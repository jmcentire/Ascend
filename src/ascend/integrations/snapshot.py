"""Performance snapshot — aggregates GitHub + Linear data into DB."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from ascend.config import AscendConfig


# Score weights
_WEIGHTS = {
    "commits_count": 1,
    "prs_opened": 3,
    "prs_merged": 5,
    "issues_completed": 5,
    "issues_in_progress": 2,
}
_MAX_SCORE = 100.0


def take_snapshot(
    member_id: int,
    member_name: str,
    github_handle: Optional[str],
    conn: sqlite3.Connection,
    config: AscendConfig,
    *,
    hours: int = 24,
    email: Optional[str] = None,
    personal_email: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    date_str: Optional[str] = None,
    skip_linear: bool = False,
    skip_fetch: bool = False,
) -> dict[str, Any]:
    """Take a performance snapshot for a single member.

    For backfill, pass explicit since/until/date_str to snapshot a specific day.
    """
    if since is None:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    metrics: dict[str, Any] = {
        "commits_count": 0,
        "prs_opened": 0,
        "prs_merged": 0,
        "issues_completed": 0,
        "issues_in_progress": 0,
    }
    errors: list[str] = []

    # GitHub data
    if github_handle:
        try:
            from ascend.integrations.github import fetch_member_github
            gh_data = fetch_member_github(
                github_handle, str(config.repos_dir), config.github_org, since,
                email=email, personal_email=personal_email, until=until,
                skip_fetch=skip_fetch,
            )
            if not gh_data.get("error"):
                metrics["commits_count"] = len(gh_data.get("commits", []))
                metrics["prs_opened"] = len(gh_data.get("prs", {}).get("open", []))
                metrics["prs_merged"] = len(gh_data.get("prs", {}).get("merged", []))
            else:
                errors.append(f"github: {gh_data['error']}")
        except Exception as e:
            errors.append(f"github: {e}")

    # Linear data
    linear_api_key = os.environ.get(config.linear_api_key_env, "") if not skip_linear else ""
    if linear_api_key:
        try:
            from ascend.integrations.linear import fetch_member_issues, get_effective_team_ids
            team_ids = get_effective_team_ids(config)
            for team_id in team_ids:
                issues = fetch_member_issues(linear_api_key, team_id, member_name, since)
                for issue in issues:
                    state = (issue.get("state", {}).get("name", "") or "").lower()
                    if "done" in state or "complete" in state:
                        metrics["issues_completed"] += 1
                    elif "progress" in state or "started" in state:
                        metrics["issues_in_progress"] += 1
        except Exception as e:
            errors.append(f"linear: {e}")
    else:
        errors.append("linear: API key not set")

    # Compute score
    raw_score = sum(metrics[k] * _WEIGHTS[k] for k in _WEIGHTS)
    score = min(raw_score, _MAX_SCORE)

    # Store in DB (upsert — re-runs on same day replace previous snapshot)
    existing = conn.execute(
        "SELECT id FROM performance_snapshots WHERE member_id = ? AND date = ? AND source = ?",
        (member_id, date_str, "sync"),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE performance_snapshots SET metrics = ?, score = ? WHERE id = ?",
            (json.dumps(metrics), score, existing["id"]),
        )
    else:
        conn.execute(
            """INSERT INTO performance_snapshots (member_id, date, source, metrics, score)
               VALUES (?, ?, ?, ?, ?)""",
            (member_id, date_str, "sync", json.dumps(metrics), score),
        )
    conn.commit()

    return {
        "member_id": member_id,
        "member_name": member_name,
        "date": date_str,
        "metrics": metrics,
        "score": score,
        "errors": errors,
    }


def take_all_snapshots(
    conn: sqlite3.Connection, config: AscendConfig, *, hours: int = 24,
    since: Optional[datetime] = None, until: Optional[datetime] = None,
    date_str: Optional[str] = None, skip_linear: bool = False,
    skip_fetch: bool = False,
) -> list[dict[str, Any]]:
    """Take snapshots for all active members with github handles."""
    rows = conn.execute(
        "SELECT id, name, github, email, personal_email FROM members WHERE status = 'active'"
    ).fetchall()

    results = []
    for row in rows:
        mid = row["id"]
        name = row["name"]
        github = row["github"]
        result = take_snapshot(
            mid, name, github, conn, config, hours=hours,
            email=row["email"], personal_email=row["personal_email"],
            since=since, until=until, date_str=date_str, skip_linear=skip_linear,
            skip_fetch=skip_fetch,
        )
        results.append(result)

    return results
