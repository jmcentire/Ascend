"""GitHub fetcher — local git log + gh pr list.

Ported from daily-report, adapted for member-centric queries.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


def _run_cmd(
    cmd: list[str], *, timeout: int = 15, max_retries: int = 2
) -> tuple[str, str, int]:
    """Run a subprocess with retry and timeout."""
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


def fetch_prs(repo_slug: str, since: datetime) -> dict[str, Any]:
    """Fetch open and recently merged PRs via gh CLI."""
    fields = "number,title,author,state,createdAt,updatedAt,mergedAt,closedAt,reviewDecision,url"

    stdout_open, stderr_open, rc_open = _run_cmd([
        "gh", "pr", "list", "--repo", repo_slug,
        "--json", fields, "--state", "open",
    ])

    since_str = since.strftime("%Y-%m-%dT%H:%M:%S")
    stdout_merged, stderr_merged, rc_merged = _run_cmd([
        "gh", "pr", "list", "--repo", repo_slug,
        "--json", fields, "--state", "merged",
        "--search", f"merged:>={since_str}",
    ])

    if rc_open != 0 and rc_merged != 0:
        return {"error": (stderr_open or stderr_merged).strip(), "open": [], "merged": []}

    open_prs = _parse_pr_list(stdout_open) if rc_open == 0 else []
    merged_prs = _parse_pr_list(stdout_merged) if rc_merged == 0 else []
    merged_prs = [pr for pr in merged_prs if _is_within_window(pr, since)]

    return {"error": None, "open": open_prs, "merged": merged_prs}


def fetch_member_github(
    github_handle: str, repos_dir: str, github_org: str, since: datetime
) -> dict[str, Any]:
    """Fetch all GitHub activity for a member across all repos."""
    repos_path = Path(repos_dir)
    if not repos_path.exists():
        return {"error": f"repos_dir not found: {repos_dir}", "commits": [], "prs": {"open": [], "merged": []}}

    all_commits: list[dict[str, Any]] = []
    all_open_prs: list[dict[str, Any]] = []
    all_merged_prs: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    seen_pr_nums: set[int] = set()

    for entry in sorted(repos_path.iterdir()):
        if not entry.is_dir() or not (entry / ".git").exists():
            continue

        # Check for commits by this author
        since_str = since.strftime("%Y-%m-%dT%H:%M:%S")
        fmt = "%H|%an|%s|%aI"
        stdout, _, rc = _run_cmd([
            "git", "-C", str(entry), "log", "--all",
            f"--author={github_handle}", f"--since={since_str}", f"--format={fmt}",
        ])
        if rc == 0:
            for line in stdout.strip().splitlines():
                if not line:
                    continue
                parts = line.split("|", 3)
                if len(parts) == 4:
                    h = parts[0][:8]
                    if h not in seen_hashes:
                        seen_hashes.add(h)
                        all_commits.append({
                            "hash": h, "author": parts[1],
                            "message": parts[2], "date": parts[3],
                            "repo": entry.name,
                        })

        # Fetch PRs for this author
        repo_slug = f"{github_org}/{entry.name}"
        pr_result = fetch_prs(repo_slug, since)
        if not pr_result.get("error"):
            for pr in pr_result.get("open", []):
                if pr.get("author") == github_handle and pr["number"] not in seen_pr_nums:
                    seen_pr_nums.add(pr["number"])
                    pr["repo"] = entry.name
                    all_open_prs.append(pr)
            for pr in pr_result.get("merged", []):
                if pr.get("author") == github_handle and pr["number"] not in seen_pr_nums:
                    seen_pr_nums.add(pr["number"])
                    pr["repo"] = entry.name
                    all_merged_prs.append(pr)

    return {
        "error": None,
        "commits": all_commits,
        "prs": {"open": all_open_prs, "merged": all_merged_prs},
    }


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


def _is_within_window(pr: dict[str, Any], since: datetime) -> bool:
    """Check if a PR was merged or closed within the time window."""
    for field in ("merged_at",):
        ts = pr.get(field, "")
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt >= since:
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
