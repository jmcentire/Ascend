"""Sync commands — github, linear, slack, snapshot."""

from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from ascend.audit import log_operation
from ascend.config import DB_PATH, load_config
from ascend.db import get_connection
from ascend.output import format_table, render_output


def _get_conn() -> sqlite3.Connection:
    return get_connection(DB_PATH)


def _resolve_member(member: str, conn: sqlite3.Connection) -> Optional[dict]:
    """Resolve member by name, github, or ID. Returns dict or None."""
    if member.isdigit():
        row = conn.execute("SELECT id, name, github, email, personal_email FROM members WHERE id = ?", (int(member),)).fetchone()
    else:
        row = conn.execute(
            "SELECT id, name, github, email, personal_email FROM members WHERE LOWER(name) = LOWER(?) OR github = ?",
            (member, member),
        ).fetchone()
    return dict(row) if row else None


def _get_since(args: argparse.Namespace, config) -> datetime:
    """Get the 'since' datetime from --hours or config default."""
    hours = getattr(args, "hours", None) or config.default_lookback_hours
    return datetime.now(timezone.utc) - timedelta(hours=int(hours))


def cmd_sync(args: argparse.Namespace) -> None:
    """Run all integrations and take snapshots."""
    config = load_config()
    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    since = _get_since(args, config)
    member_filter = getattr(args, "member", None)

    results: dict = {"github": None, "linear": None, "slack": None, "snapshots": None}

    # GitHub
    results["github"] = _run_github(member_filter, conn, config, since)

    # Linear
    results["linear"] = _run_linear(member_filter, conn, config, since)

    # Slack
    results["slack"] = _run_slack(config, since)

    # Snapshots
    hours = getattr(args, "hours", None) or config.default_lookback_hours
    results["snapshots"] = _run_snapshots(member_filter, conn, config, hours=int(hours))

    conn.close()
    log_operation("sync", args={"member": member_filter})

    if json_mode:
        render_output(results, json_mode=True)
    else:
        _print_sync_summary(results)


def cmd_sync_github(args: argparse.Namespace) -> None:
    """Fetch GitHub data."""
    config = load_config()
    conn = _get_conn()
    since = _get_since(args, config)
    member_filter = getattr(args, "member", None)

    result = _run_github(member_filter, conn, config, since)
    conn.close()
    log_operation("sync github", args={"member": member_filter})

    if getattr(args, "json", False):
        render_output(result, json_mode=True)
    else:
        _print_github_summary(result)


def cmd_sync_linear(args: argparse.Namespace) -> None:
    """Fetch Linear data."""
    config = load_config()
    conn = _get_conn()
    since = _get_since(args, config)
    member_filter = getattr(args, "member", None)

    result = _run_linear(member_filter, conn, config, since)
    conn.close()
    log_operation("sync linear", args={"member": member_filter})

    if getattr(args, "json", False):
        render_output(result, json_mode=True)
    else:
        _print_linear_summary(result)


def cmd_sync_slack(args: argparse.Namespace) -> None:
    """Fetch Slack data."""
    config = load_config()
    since = _get_since(args, config)

    result = _run_slack(config, since)
    log_operation("sync slack")

    if getattr(args, "json", False):
        render_output(result, json_mode=True)
    else:
        _print_slack_summary(result)


def cmd_sync_snapshot(args: argparse.Namespace) -> None:
    """Take performance snapshots."""
    config = load_config()
    conn = _get_conn()
    member_filter = getattr(args, "member", None)
    hours = getattr(args, "hours", None) or 24

    result = _run_snapshots(member_filter, conn, config, hours=hours)
    conn.close()
    log_operation("sync snapshot", args={"member": member_filter})

    if getattr(args, "json", False):
        render_output(result, json_mode=True)
    else:
        if not result:
            render_output("No snapshots taken.")
            return
        for s in result:
            errors = ", ".join(s.get("errors", [])) if s.get("errors") else "none"
            render_output(
                f"  {s['member_name']}: score={s['score']:.0f} "
                f"(commits={s['metrics']['commits_count']}, "
                f"prs_opened={s['metrics']['prs_opened']}, "
                f"prs_merged={s['metrics']['prs_merged']}, "
                f"issues={s['metrics']['issues_completed']}) "
                f"errors=[{errors}]"
            )
        render_output(f"\n{len(result)} snapshot(s) taken.")


def cmd_sync_backfill(args: argparse.Namespace) -> None:
    """Backfill historical snapshots from git history, day by day."""
    config = load_config()
    conn = _get_conn()
    member_filter = getattr(args, "member", None)
    days = getattr(args, "days", 30)
    skip_linear = getattr(args, "no_linear", False)
    json_mode = getattr(args, "json", False)

    from ascend.integrations.snapshot import take_snapshot, take_all_snapshots
    from ascend.integrations.github import clear_pr_cache, fetch_all_github

    # Clear PR cache and fetch all repos once upfront
    clear_pr_cache()
    if not json_mode:
        render_output("  Fetching all repos...")
    # Trigger a single fetch by calling fetch_all_github with a dummy query;
    # the parallel git fetch runs once, then per-day iterations skip it.
    fetch_all_github([], str(config.repos_dir), config.github_org,
                     datetime.now(timezone.utc))

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    all_results = []

    for day_offset in range(days, 0, -1):
        day_start = today - timedelta(days=day_offset)
        day_end = day_start + timedelta(days=1)
        date_str = day_start.strftime("%Y-%m-%d")

        if member_filter:
            m = _resolve_member(member_filter, conn)
            if not m:
                render_output(f"Member '{member_filter}' not found.")
                conn.close()
                return
            result = take_snapshot(
                m["id"], m["name"], m.get("github"), conn, config,
                since=day_start, until=day_end, date_str=date_str,
                skip_linear=skip_linear, skip_fetch=True,
                email=m.get("email"), personal_email=m.get("personal_email"),
            )
            all_results.append(result)
        else:
            day_results = take_all_snapshots(
                conn, config,
                since=day_start, until=day_end, date_str=date_str,
                skip_linear=skip_linear, skip_fetch=True,
            )
            all_results.extend(day_results)

        # Progress indicator
        if not json_mode:
            active = sum(1 for r in all_results if r["score"] > 0 and r["date"] == date_str)
            render_output(f"  {date_str}: {active} active member(s)")

    conn.close()
    log_operation("sync backfill", args={"member": member_filter, "days": days})

    if json_mode:
        render_output(all_results, json_mode=True)
    else:
        total_snaps = len(all_results)
        active_snaps = sum(1 for r in all_results if r["score"] > 0)
        render_output(f"\nBackfill complete: {total_snaps} snapshots, {active_snaps} with activity.")


# -- Internal runners --

def _run_github(member_filter, conn, config, since):
    from ascend.integrations.github import fetch_member_github, fetch_all_github, clear_pr_cache
    results = []
    if member_filter:
        m = _resolve_member(member_filter, conn)
        if m and m.get("github"):
            data = fetch_member_github(
                m["github"], str(config.repos_dir), config.github_org, since,
                email=m.get("email"), personal_email=m.get("personal_email"),
            )
            results.append({"member": m["name"], "github": m["github"], **data})
        elif m:
            results.append({"member": m["name"], "error": "no github handle"})
        else:
            return {"error": f"member '{member_filter}' not found", "results": []}
    else:
        rows = conn.execute(
            "SELECT id, name, github, email, personal_email FROM members WHERE status = 'active' AND github IS NOT NULL AND github != ''"
        ).fetchall()
        members = [{"name": r["name"], "github": r["github"], "email": r["email"], "personal_email": r["personal_email"]} for r in rows]
        clear_pr_cache()
        bulk = fetch_all_github(members, str(config.repos_dir), config.github_org, since)
        for m in members:
            handle = m["github"]
            data = bulk.get(handle, {"commits": [], "prs": {"open": [], "merged": []}})
            results.append({"member": m["name"], "github": handle, **data})
    return {"error": None, "results": results}


def _run_linear(member_filter, conn, config, since):
    from ascend.integrations.linear import fetch_member_issues, get_effective_team_ids
    api_key = os.environ.get(config.linear_api_key_env, "")
    if not api_key:
        return {"error": f"{config.linear_api_key_env} not set", "results": []}

    team_ids = get_effective_team_ids(config)
    if not team_ids:
        return {"error": "no linear team IDs configured", "results": []}

    results = []
    if member_filter:
        m = _resolve_member(member_filter, conn)
        if m:
            all_issues = []
            for tid in team_ids:
                all_issues.extend(fetch_member_issues(api_key, tid, m["name"], since))
            results.append({"member": m["name"], "issues": all_issues, "count": len(all_issues)})
        else:
            return {"error": f"member '{member_filter}' not found", "results": []}
    else:
        rows = conn.execute("SELECT id, name FROM members WHERE status = 'active'").fetchall()
        for row in rows:
            all_issues = []
            for tid in team_ids:
                all_issues.extend(fetch_member_issues(api_key, tid, row["name"], since))
            if all_issues:
                results.append({"member": row["name"], "issues": all_issues, "count": len(all_issues)})
    return {"error": None, "results": results}


def _run_slack(config, since):
    from ascend.integrations.slack import fetch_channel_activity
    token = os.environ.get(config.slack_bot_token_env, "")
    if not token:
        return {"error": f"{config.slack_bot_token_env} not set", "channels": []}

    channels = config.slack_channels or []
    if not channels:
        return {"error": "no slack channels configured", "channels": []}

    results = []
    for ch in channels:
        data = fetch_channel_activity(token, ch, since)
        results.append(data)
    return {"error": None, "channels": results}


def _run_snapshots(member_filter, conn, config, *, hours=24):
    from ascend.integrations.snapshot import take_snapshot, take_all_snapshots
    if member_filter:
        m = _resolve_member(member_filter, conn)
        if m:
            result = take_snapshot(
                m["id"], m["name"], m.get("github"), conn, config,
                hours=hours,
                email=m.get("email"), personal_email=m.get("personal_email"),
            )
            return [result]
        return []
    return take_all_snapshots(conn, config, hours=hours)


# -- Display helpers --

def _print_sync_summary(results):
    render_output("## Sync Results\n")
    render_output("### GitHub")
    _print_github_summary(results.get("github"))
    render_output("\n### Linear")
    _print_linear_summary(results.get("linear"))
    render_output("\n### Slack")
    _print_slack_summary(results.get("slack"))
    render_output("\n### Snapshots")
    snapshots = results.get("snapshots") or []
    render_output(f"  {len(snapshots)} snapshot(s) taken.")


def _print_github_summary(result):
    if not result:
        return
    if result.get("error"):
        render_output(f"  Error: {result['error']}")
        return
    for r in result.get("results", []):
        commits = len(r.get("commits", []))
        prs_open = len(r.get("prs", {}).get("open", []))
        prs_merged = len(r.get("prs", {}).get("merged", []))
        render_output(f"  {r['member']}: {commits} commits, {prs_open} open PRs, {prs_merged} merged PRs")


def _print_linear_summary(result):
    if not result:
        return
    if result.get("error"):
        render_output(f"  Error: {result['error']}")
        return
    for r in result.get("results", []):
        render_output(f"  {r['member']}: {r['count']} issues")


def _print_slack_summary(result):
    if not result:
        return
    if result.get("error"):
        render_output(f"  Error: {result['error']}")
        return
    for ch in result.get("channels", []):
        if ch.get("error"):
            render_output(f"  #{ch.get('channel', '?')}: Error — {ch['error']}")
        else:
            render_output(
                f"  #{ch['channel']}: {ch['message_count']} messages, "
                f"{ch['active_threads']} active threads, {len(ch.get('notable', []))} notable"
            )
