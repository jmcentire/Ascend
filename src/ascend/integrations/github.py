"""GitHub fetcher — local git log + gh pr list.

Ported from daily-report, adapted for member-centric queries.

Performance: PR data is fetched once per repo and cached, not once per
member per repo. With 66 repos × 29 members the naive approach would
make ~3,800 gh API calls; the cached approach makes ~132 (2 per repo).
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

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

    fields = "number,title,author,state,createdAt,updatedAt,mergedAt,closedAt,reviewDecision,url"

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
    *, until: datetime | None = None,
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
        h: {"error": None, "commits": [], "prs": {"open": [], "merged": []}}
        for h in handles
    }
    seen_hashes: dict[str, set[str]] = {h: set() for h in handles}

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

    for entry in repo_dirs:
        # Fetch ALL commits for the time window (not per-author)
        since_str = since.strftime("%Y-%m-%dT%H:%M:%S")
        fmt = "%H|%an|%ae|%s|%aI"
        log_cmd = [
            "git", "-C", str(entry), "log", "--all",
            f"--since={since_str}", f"--format={fmt}",
        ]
        if until:
            log_cmd.insert(-1, f"--until={until.strftime('%Y-%m-%dT%H:%M:%S')}")
        stdout, _, rc = _run_cmd(log_cmd)
        if rc == 0:
            for line in stdout.strip().splitlines():
                if not line:
                    continue
                parts = line.split("|", 4)
                if len(parts) != 5:
                    continue
                commit_hash, author_name, author_email, message, date = parts
                h = commit_hash[:8]
                # Match by github handle in author name/email, or by
                # known email addresses (work + personal) from roster.
                matched_handle = email_to_handle.get(author_email.lower())
                if not matched_handle:
                    for handle in handles:
                        if handle.lower() in author_name.lower() or handle.lower() in author_email.lower():
                            matched_handle = handle
                            break
                if matched_handle and h not in seen_hashes[matched_handle]:
                    seen_hashes[matched_handle].add(h)
                    result[matched_handle]["commits"].append({
                        "hash": h, "author": author_name,
                        "message": message, "date": date,
                        "repo": entry.name,
                    })

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

    return result


def fetch_member_github(
    github_handle: str, repos_dir: str, github_org: str, since: datetime,
    *, email: str | None = None, personal_email: str | None = None,
    until: datetime | None = None,
) -> dict[str, Any]:
    """Fetch all GitHub activity for a single member across all repos.

    For bulk operations, prefer fetch_all_github() which is O(repos)
    instead of O(members * repos).
    """
    member = {"github": github_handle, "email": email, "personal_email": personal_email}
    results = fetch_all_github(
        [member], repos_dir, github_org, since, until=until,
    )
    return results.get(github_handle, {
        "error": None, "commits": [], "prs": {"open": [], "merged": []},
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
            "created_at": pr.get("createdAt", ""),
            "merged_at": pr.get("mergedAt", ""),
            "url": pr.get("url", ""),
        })
    return result


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
