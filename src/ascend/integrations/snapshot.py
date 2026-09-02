"""Performance snapshot — aggregates GitHub + Linear data into DB."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from ascend.config import AscendConfig


# Visible-activity index weights.
# NOTE: this is an ACTIVITY index, not a performance verdict. It is a weighted
# sum of countable artifacts (commits/PRs/issues/reviews). Prevention leaves no
# event and craft produces states rather than artifacts — neither registers here.
# `reviews_given` and `coauthored_commits` are included so that *multiplication*
# (reviewing others' PRs, or helping land someone else's commit — work whose
# value shows up in another person's output) earns at least partial credit
# instead of being invisible. Read the index as an indicator that points to
# "look closer," never as an answer about how good someone is.
_WEIGHTS = {
    "commits_count": 1,
    "prs_opened": 3,
    "prs_merged": 5,
    "issues_completed": 5,
    "issues_in_progress": 2,
    "reviews_given": 2,
    "coauthored_commits": 1,
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
    gh_data_all: Optional[dict[str, dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Take a performance snapshot for a single member.

    For backfill, pass explicit since/until/date_str to snapshot a specific day.

    ``gh_data_all`` is a pre-fetched ``fetch_all_github`` result. Pass it whenever
    snapshotting more than one member: cross-person metrics (fixes_others,
    foundation_files) can only be derived when every roster member is resolved in
    the same pass, and it turns an O(members x repos) sync into O(repos).
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
        "reviews_given": 0,
        "coauthored_commits": 0,
        # Flow & quality signals (ANALYSIS_STANDARD.md §1.C/§1.D). These are NOT folded
        # into the activity-index score below — they are quality/latency indicators, and
        # the index stays an activity-only sum per the indicator-not-verdict doctrine.
        "stale_hours": 0.0,
        "rotting_prs": 0,
        "pr_cycle_p85_hours": 0.0,
        "open_prs": 0,
        "bug_share": 0.0,
        "reopened": 0,
        # Code volume, classified (ANALYSIS_STANDARD.md §1.5 Gate 1). Raw insertion
        # counts are not reported because they are dominated by data and generated
        # files — only ~22% of added lines in this codebase are production code.
        "prod_lines_added": 0,
        "prod_lines_deleted": 0,
        "test_lines_added": 0,
        "generated_lines_added": 0,
        "test_ratio": 0.0,
        # Rework direction (§10.2) — the strongest negative discriminator available.
        "fixed_by_others": 0,
        "fixes_others": 0,
        # Foundation share (§10.5) — files you touched first that others built on.
        "foundation_files": 0,
        "files_touched": 0,
        # Review reach (§10.4) — count alone conflates in-silo churn with real
        # multiplication.
        "reviews_cross_repo": 0,
        "review_avg_criticality": 0.0,
        # Governance (§1.5 Gate 4) — reported, never used to penalise an individual.
        "prs_merged_without_human_approval": 0,
    }
    errors: list[str] = []

    # GitHub data
    if github_handle:
        try:
            if gh_data_all is not None:
                gh_data = gh_data_all.get(github_handle) or {
                    "error": None, "commits": [], "prs": {"open": [], "merged": []},
                }
            else:
                from ascend.integrations.github import fetch_member_github
                gh_data = fetch_member_github(
                    github_handle, str(config.repos_dir), config.github_org, since,
                    email=email, personal_email=personal_email, until=until,
                    skip_fetch=skip_fetch,
                )
            if not gh_data.get("error"):
                metrics["commits_count"] = len(gh_data.get("commits", []))
                prs = gh_data.get("prs", {}) or {}
                metrics["prs_opened"] = len(prs.get("open", []))
                metrics["prs_merged"] = len(prs.get("merged", []))
                metrics["reviews_given"] = gh_data.get("reviews_given", 0)
                metrics["coauthored_commits"] = gh_data.get("coauthored_commits", 0)

                lines = gh_data.get("lines") or {}
                metrics["prod_lines_added"] = lines.get("prod_added", 0)
                metrics["prod_lines_deleted"] = lines.get("prod_deleted", 0)
                metrics["test_lines_added"] = lines.get("test_added", 0)
                metrics["generated_lines_added"] = lines.get("generated_added", 0)
                try:
                    from ascend.integrations.codestats import test_ratio
                    metrics["test_ratio"] = test_ratio(
                        {**{"prod_added": 0, "test_added": 0}, **lines}
                    )
                except Exception:
                    pass

                metrics["fixed_by_others"] = gh_data.get("fixed_by_others", 0)
                metrics["fixes_others"] = gh_data.get("fixes_others", 0)
                metrics["foundation_files"] = gh_data.get("foundation_files", 0)
                metrics["files_touched"] = gh_data.get("files_touched", 0)
                metrics["prs_merged_without_human_approval"] = gh_data.get(
                    "prs_merged_without_human_approval", 0
                )

                # Review reach: cross-repo share and the average criticality of what
                # was reviewed. Home repo = where the reviewer reviews most.
                rr = gh_data.get("review_repos") or {}
                given = gh_data.get("reviews_given", 0) or 0
                if rr and given:
                    home = max(rr, key=lambda k: rr[k])
                    metrics["reviews_cross_repo"] = sum(
                        n for r, n in rr.items() if r != home
                    )
                if given:
                    metrics["review_avg_criticality"] = round(
                        gh_data.get("review_criticality_sum", 0.0) / given, 2
                    )
                # Flow & latency metrics (§1.C) — derived from the PR data already fetched,
                # so no extra network cost.
                try:
                    from ascend.integrations.github import compute_flow_metrics
                    flow = compute_flow_metrics(prs)
                    metrics["stale_hours"] = flow.get("stale_hours", 0.0)
                    metrics["rotting_prs"] = flow.get("rotting_prs", 0)
                    metrics["pr_cycle_p85_hours"] = flow.get("pr_cycle_p85_hours", 0.0)
                    metrics["open_prs"] = flow.get("open_prs", 0)
                except Exception as e:
                    errors.append(f"github flow: {e}")
            else:
                errors.append(f"github: {gh_data['error']}")
        except Exception as e:
            errors.append(f"github: {e}")

    # Linear data
    linear_api_key = os.environ.get(config.linear_api_key_env, "") if not skip_linear else ""
    if linear_api_key:
        try:
            from ascend.integrations.linear import (
                fetch_member_issues, get_effective_team_ids, bug_share, count_reopened,
            )
            team_ids = get_effective_team_ids(config)
            all_issues: list[dict] = []
            for team_id in team_ids:
                issues = fetch_member_issues(linear_api_key, team_id, member_name, since)
                all_issues.extend(issues)
                for issue in issues:
                    state = (issue.get("state", {}).get("name", "") or "").lower()
                    if "done" in state or "complete" in state:
                        metrics["issues_completed"] += 1
                    elif "progress" in state or "started" in state:
                        metrics["issues_in_progress"] += 1
                # Repeated failures (§1.D, heaviest-weighted) — reopened transitions.
                try:
                    metrics["reopened"] += count_reopened(
                        linear_api_key, team_id, member_name, since
                    )
                except Exception as e:
                    errors.append(f"linear reopened: {e}")
            # Bug-fix share (§1.D) across all issues touched this window.
            metrics["bug_share"] = bug_share(all_issues)
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

    # One GitHub pass for the whole roster. Required for correctness, not just
    # speed: fixes_others and foundation_files are cross-person and cannot be
    # derived when each member is fetched in isolation.
    gh_data_all = None
    try:
        from ascend.integrations.github import fetch_all_github
        _since = since or (datetime.now(timezone.utc) - timedelta(hours=hours))
        members_for_gh = [
            {"github": r["github"], "email": r["email"],
             "personal_email": r["personal_email"]}
            for r in rows if r["github"]
        ]
        if members_for_gh:
            gh_data_all = fetch_all_github(
                members_for_gh, str(config.repos_dir), config.github_org, _since,
                until=until, skip_fetch=skip_fetch,
            )
    except Exception:
        gh_data_all = None  # fall back to per-member fetches

    results = []
    for row in rows:
        mid = row["id"]
        name = row["name"]
        github = row["github"]
        result = take_snapshot(
            mid, name, github, conn, config, hours=hours,
            email=row["email"], personal_email=row["personal_email"],
            since=since, until=until, date_str=date_str, skip_linear=skip_linear,
            skip_fetch=skip_fetch, gh_data_all=gh_data_all,
        )
        results.append(result)

    return results
