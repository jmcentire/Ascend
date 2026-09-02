"""GitHub fetcher — local git log + gh pr list.

Ported from daily-report, adapted for member-centric queries.

Performance: PR data is fetched once per repo and cached, not once per
member per repo. With 66 repos × 29 members the naive approach would
make ~3,800 gh API calls; the cached approach makes ~132 (2 per repo).
"""

from __future__ import annotations

import concurrent.futures
from collections import defaultdict
import json
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from ascend.integrations import codestats
from ascend.analysis.cohorts import DEFAULT_CRITICALITY

# Reviews authored by machines are not multiplication. 93% of inline review threads in
# this org are bot-authored (Cursor, Adapt, Codex, Copilot), so any review metric that
# includes them measures CI, not people. ANALYSIS_STANDARD.md §1.5 Gate 4.
REVIEW_BOTS = {
    "cursor", "adaptcom", "chatgpt-codex-connector", "copilot-pull-request-reviewer",
    "claude", "sealabcore", "github-actions", "dependabot", "wander-ci",
}

# A commit whose subject matches this is repair work. Used for rework direction:
# a fix by SOMEONE ELSE landing on a file you just touched is the strongest negative
# discriminator found (§1.5 / §10.2) — it beat every volume metric.
_FIXY = re.compile(
    r"\b(fix|bug|hotfix|patch|revert|repair|regression|broken|incident)\b", re.I
)
_REWORK_WINDOW_SECONDS = 14 * 86400


def _is_review_bot(login: str) -> bool:
    l = (login or "").lower()
    return l in REVIEW_BOTS or l.endswith("[bot]")


def _criticality_of(repo_name: str) -> str:
    """Blast-radius class for a repo (§1.D system-criticality control)."""
    low = (repo_name or "").lower()
    for frag, cls in DEFAULT_CRITICALITY.items():
        if frag in low:
            return cls
    return "standard"


_CRIT_WEIGHT = {"critical": 3.0, "high": 2.5, "standard": 2.0, "low": 1.0}


# Module-level PR cache: repo_slug -> {"open": [...], "merged": [...]}
_pr_cache: dict[str, dict[str, Any]] = {}


def _run_cmd(
    cmd: list[str], *, timeout: int = 15, max_retries: int = 1
) -> tuple[str, str, int]:
    """Run a subprocess with retry and timeout.  Fail fast on errors."""
    for attempt in range(max_retries + 1):
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
            )
            if result.returncode != 0 and attempt < max_retries:
                err = result.stderr.lower()
                if any(s in err for s in ("rate limit", "502", "503", "timeout")):
                    continue
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            if attempt < max_retries:
                continue
            return "", "timeout", 1
    return "", "max retries exceeded", 1


def fetch_commits(
    repos_dir: str, repo_name: str, branch: str, since: datetime
) -> dict[str, Any]:
    """Fetch recent commits from local git repo."""
    repo_path = Path(repos_dir) / repo_name.lower()
    if not repo_path.exists():
        return {"error": f"repo not found: {repo_path}", "data": []}

    # Try fetching from remote
    warning = None
    _, fetch_err, fetch_rc = _run_cmd(
        ["git", "-C", str(repo_path), "fetch", "origin", branch, "-q"]
    )
    if fetch_rc != 0:
        # Try fallback branches
        for fallback in ("main", "master"):
            if fallback == branch:
                continue
            _, _, frc = _run_cmd(
                ["git", "-C", str(repo_path), "fetch", "origin", fallback, "-q"]
            )
            if frc == 0:
                branch = fallback
                break
        else:
            warning = f"git fetch failed: {fetch_err.strip()}"

    since_str = since.strftime("%Y-%m-%dT%H:%M:%S")
    fmt = "%H|%an|%s|%aI"
    stdout, stderr, rc = _run_cmd([
        "git", "-C", str(repo_path), "log",
        f"origin/{branch}", f"--since={since_str}", f"--format={fmt}",
    ])

    if rc != 0:
        return {"error": stderr.strip(), "data": [], "warning": warning}

    commits = []
    for line in stdout.strip().splitlines():
        if not line:
            continue
        parts = line.split("|", 3)
        if len(parts) == 4:
            commits.append({
                "hash": parts[0][:8],
                "author": parts[1],
                "message": parts[2],
                "date": parts[3],
            })

    return {"error": None, "data": commits, "warning": warning}


def fetch_prs(
    repo_slug: str, since: datetime, *, until: datetime | None = None,
) -> dict[str, Any]:
    """Fetch open and recently merged PRs via gh CLI.  Results are cached."""
    if repo_slug in _pr_cache:
        cached = _pr_cache[repo_slug]
        # Re-filter merged PRs for the current time window
        merged = [pr for pr in cached.get("all_merged", [])
                  if _is_within_window(pr, since, until=until)]
        return {"error": cached.get("error"), "open": cached.get("open", []), "merged": merged}

    fields = "number,title,author,state,createdAt,updatedAt,mergedAt,closedAt,reviewDecision,latestReviews,mergedBy,url"

    stdout_open, stderr_open, rc_open = _run_cmd([
        "gh", "pr", "list", "--repo", repo_slug,
        "--json", fields, "--state", "open", "--limit", "100",
    ])

    since_str = since.strftime("%Y-%m-%dT%H:%M:%S")
    stdout_merged, stderr_merged, rc_merged = _run_cmd([
        "gh", "pr", "list", "--repo", repo_slug,
        "--json", fields, "--state", "merged",
        "--search", f"merged:>={since_str}", "--limit", "100",
    ])

    if rc_open != 0 and rc_merged != 0:
        err = (stderr_open or stderr_merged).strip()
        _pr_cache[repo_slug] = {"error": err, "open": [], "all_merged": []}
        return {"error": err, "open": [], "merged": []}

    open_prs = _parse_pr_list(stdout_open) if rc_open == 0 else []
    all_merged = _parse_pr_list(stdout_merged) if rc_merged == 0 else []
    merged_prs = [pr for pr in all_merged if _is_within_window(pr, since, until=until)]

    _pr_cache[repo_slug] = {"error": None, "open": open_prs, "all_merged": all_merged}
    return {"error": None, "open": open_prs, "merged": merged_prs}


def clear_pr_cache() -> None:
    """Clear the PR cache (call between sync runs if needed)."""
    _pr_cache.clear()


def fetch_all_github(
    members: list[dict[str, str]], repos_dir: str, github_org: str, since: datetime,
    *, until: datetime | None = None, skip_fetch: bool = False,
) -> dict[str, dict[str, Any]]:
    """Fetch GitHub activity for all members efficiently.

    Iterates repos once, collects commits for all members via git log,
    fetches PRs once per repo (cached), then distributes results.
    Returns {github_handle: {commits: [...], prs: {open: [...], merged: [...]}}}.
    """
    repos_path = Path(repos_dir)
    if not repos_path.exists():
        return {m["github"]: {"error": f"repos_dir not found", "commits": [], "prs": {"open": [], "merged": []}}
                for m in members}

    handles = {m["github"] for m in members if m.get("github")}
    result: dict[str, dict[str, Any]] = {
        h: {"error": None, "commits": [], "prs": {"open": [], "merged": []},
            "reviews_given": 0, "coauthored_commits": 0,
            "reviews_cross_repo": 0, "review_criticality_sum": 0.0,
            "prs_merged_without_human_approval": 0, "prs_merged_total": 0,
            "lines": codestats.empty_line_stats(),
            "fixes_others": 0, "fixed_by_others": 0,
            "foundation_files": 0, "files_touched": 0}
        for h in handles
    }
    seen_hashes: dict[str, set[str]] = {h: set() for h in handles}
    seen_coauthor: set[tuple[str, str]] = set()

    # Build email-to-handle lookup so commits authored with personal/work
    # emails are attributed correctly even when the email doesn't contain
    # the GitHub handle.
    email_to_handle: dict[str, str] = {}
    for m in members:
        gh = m.get("github")
        if not gh:
            continue
        for key in ("email", "personal_email"):
            addr = m.get(key)
            if addr:
                email_to_handle[addr.lower()] = gh

    repo_dirs = sorted(
        e for e in repos_path.iterdir()
        if e.is_dir() and (e / ".git").exists()
    )

    # Fetch all repos in parallel so git log sees latest remote state
    if not skip_fetch:
        def _fetch_repo(repo: Path) -> None:
            _run_cmd(["git", "-C", str(repo), "fetch", "--all", "-q"], timeout=30)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            pool.map(_fetch_repo, repo_dirs)

    touch_index: dict[tuple[str, str], list[tuple[int, Any, bool]]] = defaultdict(list)

    for entry in repo_dirs:
        # Fetch ALL commits for the time window (not per-author). Body (%b) is
        # included so Co-authored-by trailers can be credited as multiplication.
        # Fields are separated by \x1f and commits by \x1e so multi-line bodies
        # parse cleanly.
        since_str = since.strftime("%Y-%m-%dT%H:%M:%S")
        fmt = "%x1e%H%x1f%an%x1f%ae%x1f%s%x1f%aI%x1f%at%x1f%b"
        log_cmd = [
            "git", "-C", str(entry), "log", "--all", "--no-merges", "--numstat",
            f"--since={since_str}", f"--format={fmt}",
        ]
        if until:
            log_cmd.insert(-1, f"--until={until.strftime('%Y-%m-%dT%H:%M:%S')}")
        stdout, _, rc = _run_cmd(log_cmd)
        if rc == 0:
            for c in _parse_commit_records(stdout):
                h = c["hash"][:8]
                # Match by github handle in author name/email, or by
                # known email addresses (work + personal) from roster.
                matched_handle = _match_handle(
                    c["author_name"], c["author_email"], handles, email_to_handle
                )
                if matched_handle and h not in seen_hashes[matched_handle]:
                    seen_hashes[matched_handle].add(h)
                    result[matched_handle]["commits"].append({
                        "hash": h, "author": c["author_name"],
                        "message": c["message"], "date": c["date"],
                        "repo": entry.name,
                    })
                    # Classified line accounting (§1.5 Gate 1) — raw insertion
                    # counts are meaningless without this.
                    for path, added, deleted in c.get("files", []):
                        codestats.accumulate(
                            result[matched_handle]["lines"], path, added, deleted
                        )
                # File-touch index feeds rework direction and foundation share
                # (§10.2, §10.5). Recorded for every commit, matched or not, so
                # "someone else fixed it" stays detectable when the fixer is
                # off-roster.
                if c.get("files"):
                    _is_fix = bool(_FIXY.search(c.get("message") or ""))
                    _ts = c.get("ts", 0)
                    for path, _a, _d in c["files"]:
                        touch_index[(entry.name, path)].append(
                            (_ts, matched_handle, _is_fix)
                        )
                # Multiplication: credit co-authors (helped land someone else's
                # commit) — counted once per (co-author, commit), never the
                # primary author crediting themselves.
                for co_name, co_email in _parse_coauthors(c["body"]):
                    co_handle = _match_handle(co_name, co_email, handles, email_to_handle)
                    if co_handle and co_handle != matched_handle and (co_handle, h) not in seen_coauthor:
                        seen_coauthor.add((co_handle, h))
                        result[co_handle]["coauthored_commits"] += 1

        # Fetch PRs once per repo (cached)
        repo_slug = f"{github_org}/{entry.name}"
        pr_result = fetch_prs(repo_slug, since, until=until)
        if pr_result.get("error"):
            continue

        for pr in pr_result.get("open", []):
            author = pr.get("author", "")
            if author in handles:
                pr_copy = {**pr, "repo": entry.name}
                result[author]["prs"]["open"].append(pr_copy)

        for pr in pr_result.get("merged", []):
            author = pr.get("author", "")
            if author in handles:
                pr_copy = {**pr, "repo": entry.name}
                result[author]["prs"]["merged"].append(pr_copy)

        # Multiplication: credit reviews given on others' PRs in this repo.
        _tally_reviews_given(
            list(pr_result.get("open", [])) + list(pr_result.get("merged", [])),
            handles, result, repo_name=entry.name,
        )

        # Governance: merged with no human approval (§1.5 Gate 4). Self-merge is
        # the norm here, so this is reported, never used to penalise an individual.
        for pr in pr_result.get("merged", []):
            author = pr.get("author", "")
            if author in handles:
                result[author]["prs_merged_total"] += 1
                if pr.get("human_approvals", 0) == 0:
                    result[author]["prs_merged_without_human_approval"] += 1

    _tally_rework_and_foundation(touch_index, result)
    return result


def fetch_member_github(
    github_handle: str, repos_dir: str, github_org: str, since: datetime,
    *, email: str | None = None, personal_email: str | None = None,
    until: datetime | None = None, skip_fetch: bool = False,
) -> dict[str, Any]:
    """Fetch all GitHub activity for a single member across all repos.

    For bulk operations, prefer fetch_all_github() which is O(repos)
    instead of O(members * repos).
    """
    member = {"github": github_handle, "email": email, "personal_email": personal_email}
    results = fetch_all_github(
        [member], repos_dir, github_org, since, until=until, skip_fetch=skip_fetch,
    )
    return results.get(github_handle, {
        "error": None, "commits": [], "prs": {"open": [], "merged": []},
        "reviews_given": 0, "coauthored_commits": 0,
        "reviews_cross_repo": 0, "review_criticality_sum": 0.0,
        "prs_merged_without_human_approval": 0, "prs_merged_total": 0,
        "lines": codestats.empty_line_stats(),
        "fixes_others": 0, "fixed_by_others": 0,
        "foundation_files": 0, "files_touched": 0,
    })


def _parse_pr_list(stdout: str) -> list[dict[str, Any]]:
    """Parse gh pr list JSON output."""
    try:
        prs = json.loads(stdout) if stdout.strip() else []
    except json.JSONDecodeError:
        return []

    result = []
    for pr in prs:
        author = pr.get("author", {})
        author_login = author.get("login", "") if isinstance(author, dict) else ""
        review = pr.get("reviewDecision", "")
        result.append({
            "number": pr.get("number"),
            "title": pr.get("title", ""),
            "author": author_login,
            "state": pr.get("state", ""),
            "review_status": _review_label(review),
            "reviewers": _extract_reviewers(pr),
            "created_at": pr.get("createdAt", ""),
            "merged_at": pr.get("mergedAt", ""),
            "merged_by": (pr.get("mergedBy") or {}).get("login", "") if isinstance(pr.get("mergedBy"), dict) else "",
            "human_approvals": _count_human_reviews(pr, "APPROVED"),
            "human_changes_requested": _count_human_reviews(pr, "CHANGES_REQUESTED"),
            "url": pr.get("url", ""),
        })
    return result


def _extract_reviewers(pr: dict[str, Any]) -> list[str]:
    """Reviewer logins who left an actual review on a PR (from latestReviews)."""
    reviewers = []
    for r in pr.get("latestReviews") or []:
        author = r.get("author") or {}
        login = author.get("login", "") if isinstance(author, dict) else ""
        state = (r.get("state") or "").upper()
        if login and not _is_review_bot(login) and state in (
            "APPROVED", "CHANGES_REQUESTED", "COMMENTED"
        ):
            reviewers.append(login)
    return reviewers


def _count_human_reviews(pr: dict[str, Any], want_state: str) -> int:
    """Count non-bot reviews on a PR in a given state (§1.5 Gate 4)."""
    n = 0
    for r in pr.get("latestReviews") or []:
        author = r.get("author") or {}
        login = author.get("login", "") if isinstance(author, dict) else ""
        if login and not _is_review_bot(login) and (r.get("state") or "").upper() == want_state:
            n += 1
    return n


def _tally_reviews_given(
    prs: list[dict[str, Any]], handles: set[str], result: dict[str, dict[str, Any]],
    *, repo_name: str = "",
) -> None:
    """Count reviews each in-roster member gave on OTHERS' PRs.

    This is a multiplication signal: reviewing someone else's PR is work whose
    value lands in the author's output, not the reviewer's own commit/PR counts.
    Self-reviews and reviews by people outside the roster are not counted.
    """
    for pr in prs:
        author = pr.get("author", "")
        for reviewer in pr.get("reviewers", []) or []:
            if reviewer in handles and reviewer != author and not _is_review_bot(reviewer):
                result[reviewer]["reviews_given"] = result[reviewer].get("reviews_given", 0) + 1
                # Reach, not just count (§10.4): a reviewer with 956 reviews at 9%
                # cross-repo and criticality 1.10 is not multiplying at the same
                # altitude as one at 93% cross-repo and 2.75. Home repo is resolved
                # after the loop, so record the repo and weight here.
                result[reviewer].setdefault("review_repos", defaultdict(int))
                result[reviewer]["review_repos"][repo_name] += 1
                result[reviewer]["review_criticality_sum"] = (
                    result[reviewer].get("review_criticality_sum", 0.0)
                    + _CRIT_WEIGHT.get(_criticality_of(repo_name), 2.0)
                )


def _tally_rework_and_foundation(
    touch_index: dict[tuple[str, str], list[tuple[int, Any, bool]]],
    result: dict[str, dict[str, Any]],
) -> None:
    """Derive rework direction and foundation share from the file-touch index.

    Rework direction (§10.2) is the strongest negative discriminator available: for
    each repair-flagged commit, credit the NEAREST PRIOR toucher of that file within
    14 days. A fix by someone else on your recent work counts against durability;
    fixing your own counts as neither. Fixing OTHERS' work is a seniority signal and
    is credited to the fixer.

    Foundation share (§10.5) is the count of files a person touched first in the
    window that somebody else subsequently built on.
    """
    for (_repo, _path), events in touch_index.items():
        events.sort(key=lambda e: e[0])
        authors = {h for _t, h, _f in events if h}
        first_author = next((h for _t, h, _f in events if h), None)
        if first_author:
            result.setdefault(first_author, {})
            if "files_touched" in result[first_author]:
                result[first_author]["files_touched"] += 1
                if len(authors) > 1:
                    result[first_author]["foundation_files"] += 1
        for i, (ts, handle, is_fix) in enumerate(events):
            if not is_fix:
                continue
            for j in range(i - 1, -1, -1):
                prev_ts, prev_handle, _ = events[j]
                if ts - prev_ts > _REWORK_WINDOW_SECONDS:
                    break
                if prev_handle is None:
                    break
                if prev_handle == handle:
                    break  # self-repair: neither credited nor penalised
                if prev_handle in result and "fixed_by_others" in result[prev_handle]:
                    result[prev_handle]["fixed_by_others"] += 1
                if handle and handle in result and "fixes_others" in result[handle]:
                    result[handle]["fixes_others"] += 1
                break


def _match_handle(
    name: str, email: str, handles: set[str], email_to_handle: dict[str, str]
) -> str | None:
    """Resolve a commit (name, email) to a roster GitHub handle, or None."""
    handle = email_to_handle.get((email or "").lower())
    if handle:
        return handle
    for h in handles:
        if h.lower() in (name or "").lower() or h.lower() in (email or "").lower():
            return h
    return None


def _parse_commit_records(stdout: str) -> list[dict[str, Any]]:
    """Parse \\x1e-delimited git log records (fields split by \\x1f).

    Format: hash, author_name, author_email, subject, date, unix_ts, body.
    The record separator LEADS each record (``%x1e`` first in the format string):
    with --numstat git emits the stat rows after the formatted header, so a
    trailing separator would attach a commit's files to the following record.
    The numstat rows ("added\\tdeleted\\tpath") trailing the body are collected
    into ``files`` so line counts can be classified (§1.5 Gate 1).
    Body may span multiple lines; the separators keep records unambiguous.
    """
    records = []
    for rec in stdout.split("\x1e"):
        rec = rec.strip("\n")
        if not rec.strip():
            continue
        parts = rec.split("\x1f")
        if len(parts) < 6:
            continue
        # numstat rows trail the body inside the final field
        tail = parts[6] if len(parts) > 6 else ""
        body_lines, files = [], []
        for line in tail.split("\n"):
            cols = line.split("\t")
            if len(cols) == 3 and (cols[0].isdigit() or cols[0] == "-"):
                added = int(cols[0]) if cols[0].isdigit() else 0
                deleted = int(cols[1]) if cols[1].isdigit() else 0
                files.append((cols[2], added, deleted))
            else:
                body_lines.append(line)
        try:
            ts = int(parts[5])
        except (TypeError, ValueError):
            ts = 0
        records.append({
            "hash": parts[0],
            "author_name": parts[1],
            "author_email": parts[2],
            "message": parts[3],
            "date": parts[4],
            "ts": ts,
            "body": "\n".join(body_lines),
            "files": files,
        })
    return records


_COAUTHOR_RE = re.compile(
    r"^\s*co-authored-by:\s*(.*?)\s*<([^>]+)>\s*$", re.IGNORECASE | re.MULTILINE
)


def _parse_coauthors(body: str) -> list[tuple[str, str]]:
    """Extract (name, email) pairs from Co-authored-by trailers in a commit body."""
    return [(m.group(1).strip(), m.group(2).strip()) for m in _COAUTHOR_RE.finditer(body or "")]


def _is_within_window(
    pr: dict[str, Any], since: datetime, *, until: datetime | None = None,
) -> bool:
    """Check if a PR was merged within the time window [since, until)."""
    for field in ("merged_at",):
        ts = pr.get(field, "")
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt >= since and (until is None or dt < until):
                    return True
            except (ValueError, TypeError):
                continue
    return False


def _review_label(decision: str) -> str:
    """Map GitHub reviewDecision to human label."""
    return {
        "APPROVED": "approved",
        "CHANGES_REQUESTED": "changes requested",
        "REVIEW_REQUIRED": "needs review",
    }.get(decision or "", "needs review")


# ---------------------------------------------------------------------------
# Flow & latency collectors (ANALYSIS_STANDARD §1.C)
# ---------------------------------------------------------------------------


def _parse_iso(ts: Any) -> datetime | None:
    """Parse an ISO8601 timestamp (with optional trailing 'Z') to an aware UTC
    datetime. Returns None on missing/unparseable input. Never raises."""
    if not isinstance(ts, str) or not ts.strip():
        return None
    try:
        dt = datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _percentile(values: list[float], pct: float) -> float:
    """Linear-interpolation percentile (pct in [0, 100]). 0.0 for empty input."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (pct / 100.0) * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return float(ordered[lo] + (ordered[hi] - ordered[lo]) * frac)


def compute_flow_metrics(
    prs: dict[str, Any], *, now: datetime | None = None
) -> dict[str, Any]:
    """Flow & latency metrics (ANALYSIS_STANDARD §1.C) over a member's PRs.

    ``prs`` is shaped ``{"open": [...], "merged": [...]}`` where each PR is a
    raw dict with camelCase keys (createdAt, updatedAt, mergedAt). Timestamps
    are ISO8601 strings that may end in 'Z'. PRs with missing/unparseable
    timestamps are skipped gracefully (never raise).

    Returns:
        stale_hours: sum over OPEN prs of hours since updatedAt.
        rotting_prs: count of OPEN prs idle >= 7 days by updatedAt.
        pr_cycle_p85_hours: 85th percentile of (mergedAt - createdAt) in hours
            over MERGED prs; 0.0 if none parseable.
        open_prs: count of OPEN prs supplied.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    open_prs = list((prs or {}).get("open") or [])
    merged_prs = list((prs or {}).get("merged") or [])

    rotting_cutoff = timedelta(days=7)
    stale_hours = 0.0
    rotting = 0
    for pr in open_prs:
        if not isinstance(pr, dict):
            continue
        updated = _parse_iso(pr.get("updatedAt"))
        if updated is None:
            continue
        idle = now - updated
        idle_hours = idle.total_seconds() / 3600.0
        if idle_hours > 0:
            stale_hours += idle_hours
        if idle >= rotting_cutoff:
            rotting += 1

    cycle_hours: list[float] = []
    for pr in merged_prs:
        if not isinstance(pr, dict):
            continue
        created = _parse_iso(pr.get("createdAt"))
        merged = _parse_iso(pr.get("mergedAt"))
        if created is None or merged is None:
            continue
        delta_hours = (merged - created).total_seconds() / 3600.0
        if delta_hours >= 0:
            cycle_hours.append(delta_hours)

    return {
        "stale_hours": stale_hours,
        "rotting_prs": rotting,
        "pr_cycle_p85_hours": _percentile(cycle_hours, 85.0),
        "open_prs": len(open_prs),
    }


# ---------------------------------------------------------------------------
# Tenure / ramp collectors (ANALYSIS_STANDARD §3)
# ---------------------------------------------------------------------------


def first_commit_date(
    github_handle: str,
    repos_dir: str,
    *,
    email: str | None = None,
    personal_email: str | None = None,
) -> str | None:
    """Earliest commit date (ISO 'YYYY-MM-DD') authored by this person across
    all git repos under ``repos_dir``.

    Matches by author email(s) and by the GitHub handle (substring of author
    name/email). Returns None if no matching commit is found anywhere.
    """
    repos_path = Path(repos_dir)
    if not repos_path.exists():
        return None

    patterns: list[str] = []
    for addr in (email, personal_email):
        if addr and addr.strip():
            patterns.append(addr.strip())
    if github_handle and github_handle.strip():
        patterns.append(github_handle.strip())
    if not patterns:
        return None

    try:
        repo_dirs = sorted(
            e for e in repos_path.iterdir()
            if e.is_dir() and (e / ".git").exists()
        )
    except OSError:
        return None

    earliest: datetime | None = None
    for entry in repo_dirs:
        for pat in patterns:
            stdout, _, rc = _run_cmd([
                "git", "-C", str(entry), "log", "--all", "--reverse",
                "--format=%aI", f"--author={pat}", "-i",
            ])
            if rc != 0 or not stdout.strip():
                continue
            first_line = stdout.strip().splitlines()[0].strip()
            dt = _parse_iso(first_line)
            if dt is None:
                continue
            if earliest is None or dt < earliest:
                earliest = dt
            # First match per repo is the earliest for that pattern; keep
            # scanning other patterns in case a different email is older.

    if earliest is None:
        return None
    return earliest.date().isoformat()


def tenure_weeks(
    first_commit_iso: str | None, *, now: datetime | None = None
) -> float | None:
    """Weeks elapsed since the first commit date. None if input is None.

    Accepts an ISO date ('YYYY-MM-DD') or full ISO8601 timestamp.
    """
    if first_commit_iso is None:
        return None
    first = _parse_iso(first_commit_iso)
    if first is None:
        # Bare date won't parse via fromisoformat on all versions if it has a
        # trailing space etc.; try a plain date parse as a fallback.
        try:
            first = datetime.fromisoformat(first_commit_iso.strip())
            if first.tzinfo is None:
                first = first.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError, AttributeError):
            return None

    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    return (now - first).total_seconds() / (7 * 24 * 3600.0)
