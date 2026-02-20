"""Report commands — performance, team, progress, git, dashboard, custom."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Optional

from ascend.audit import log_operation
from ascend.config import DB_PATH, load_config
from ascend.db import get_connection
from ascend.output import format_table, render_output


def _get_conn() -> sqlite3.Connection:
    return get_connection(DB_PATH)


def _resolve_member(identifier: str, conn: sqlite3.Connection) -> Optional[dict]:
    """Resolve member by name, github, email, or ID."""
    if identifier.isdigit():
        row = conn.execute("SELECT * FROM members WHERE id = ?", (int(identifier),)).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM members WHERE LOWER(name) = LOWER(?) OR github = ? OR email = ?",
            (identifier, identifier, identifier),
        ).fetchone()
    return dict(row) if row else None


def _date_range(args: argparse.Namespace) -> tuple[str, str]:
    """Get date range from args, defaulting to last 30 days."""
    days = getattr(args, "days", None) or 30
    to_date = getattr(args, "to_date", None)
    from_date = getattr(args, "from_date", None)
    if to_date:
        try:
            datetime.strptime(to_date, "%Y-%m-%d")
        except ValueError:
            to_date = None
    if from_date:
        try:
            datetime.strptime(from_date, "%Y-%m-%d")
        except ValueError:
            from_date = None
    if not to_date:
        to_date = datetime.now().strftime("%Y-%m-%d")
    if not from_date:
        from_dt = datetime.strptime(to_date, "%Y-%m-%d") - timedelta(days=int(days))
        from_date = from_dt.strftime("%Y-%m-%d")
    return from_date, to_date


def _get_snapshots(conn: sqlite3.Connection, member_id: int, from_date: str, to_date: str) -> list[dict]:
    rows = conn.execute(
        """SELECT date, source, metrics, score FROM performance_snapshots
           WHERE member_id = ? AND date >= ? AND date <= ?
           ORDER BY date""",
        (member_id, from_date, to_date),
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["metrics"] = json.loads(d["metrics"]) if d["metrics"] else {}
        result.append(d)
    return result


def _get_meetings(conn: sqlite3.Connection, member_id: int, from_date: str, to_date: str) -> list[dict]:
    rows = conn.execute(
        """SELECT id, date, source, summary, sentiment_score FROM meetings
           WHERE member_id = ? AND date >= ? AND date <= ?
           ORDER BY date""",
        (member_id, from_date, to_date),
    ).fetchall()
    return [dict(r) for r in rows]


def _get_open_items(conn: sqlite3.Connection, member_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT mi.id, mi.kind, mi.content, mi.created_at, m.date as meeting_date
           FROM meeting_items mi
           JOIN meetings m ON m.id = mi.meeting_id
           WHERE m.member_id = ? AND mi.status = 'open'
           ORDER BY mi.created_at""",
        (member_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _get_flags(conn: sqlite3.Connection, member_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT flag FROM member_flags WHERE member_id = ?", (member_id,)
    ).fetchall()
    return [r["flag"] for r in rows]


def _aggregate_metrics(snapshots: list[dict]) -> dict[str, int]:
    """Sum up metrics across snapshots."""
    totals: dict[str, int] = {
        "commits_count": 0,
        "prs_opened": 0,
        "prs_merged": 0,
        "issues_completed": 0,
        "issues_in_progress": 0,
    }
    for s in snapshots:
        m = s.get("metrics", {})
        for k in totals:
            totals[k] += m.get(k, 0)
    return totals


def _compute_velocity(snapshots: list[dict], window_days: int = 28) -> float:
    """Compute weekly velocity from snapshot scores."""
    if not snapshots:
        return 0.0
    cutoff = (datetime.now() - timedelta(days=window_days)).strftime("%Y-%m-%d")
    recent = [s for s in snapshots if s["date"] >= cutoff]
    if not recent:
        return 0.0
    total_score = sum(s.get("score", 0) or 0 for s in recent)
    weeks = max(1, window_days / 7)
    return round(total_score / weeks, 1)


def _compute_momentum(snapshots: list[dict]) -> float:
    """4-week vs prior 4-week score change."""
    cutoff_recent = (datetime.now() - timedelta(days=28)).strftime("%Y-%m-%d")
    cutoff_prior = (datetime.now() - timedelta(days=56)).strftime("%Y-%m-%d")
    recent = [s for s in snapshots if s["date"] >= cutoff_recent]
    prior = [s for s in snapshots if cutoff_prior <= s["date"] < cutoff_recent]
    recent_total = sum(s.get("score", 0) or 0 for s in recent)
    prior_total = sum(s.get("score", 0) or 0 for s in prior)
    return round(recent_total - prior_total, 1)


def _member_status(snapshots: list[dict], flags: list[str]) -> str:
    """Heuristic status for a member."""
    if "pip" in flags:
        return "PIP"
    if "pto" in flags:
        return "PTO"
    if not snapshots:
        return "No Data"
    recent = [s for s in snapshots if s["date"] >= (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")]
    if not recent:
        return "Quiet"
    avg_score = sum(s.get("score", 0) for s in recent) / len(recent)
    if avg_score >= 15:
        return "Active"
    elif avg_score >= 5:
        return "On Track"
    else:
        return "Quiet"


def _get_team_members(conn: sqlite3.Connection, team_name: str) -> tuple[Optional[dict], list[dict]]:
    """Resolve team and return (team_dict, members_list)."""
    if team_name.isdigit():
        team_row = conn.execute("SELECT * FROM teams WHERE id = ?", (int(team_name),)).fetchone()
    else:
        team_row = conn.execute(
            "SELECT * FROM teams WHERE LOWER(name) = LOWER(?)", (team_name,)
        ).fetchone()
    if not team_row:
        return None, []
    team = dict(team_row)
    members = [dict(r) for r in conn.execute(
        """SELECT m.* FROM members m
           JOIN team_members tm ON tm.member_id = m.id
           WHERE tm.team_id = ? AND m.status = 'active'""",
        (team["id"],),
    ).fetchall()]
    return team, members


# ---- Report: Performance (individual member) ----

def cmd_report_performance(args: argparse.Namespace) -> None:
    """Individual performance report."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    copy = getattr(args, "copy", False)
    member_filter = getattr(args, "member", None)
    team_filter = getattr(args, "team", None)
    from_date, to_date = _date_range(args)

    if member_filter:
        m = _resolve_member(member_filter, conn)
        if not m:
            conn.close()
            render_output({"error": f"member '{member_filter}' not found"}, json_mode=True)
            return
        members = [m]
    elif team_filter:
        team, members = _get_team_members(conn, team_filter)
        if not team:
            conn.close()
            render_output({"error": f"team '{team_filter}' not found"}, json_mode=True)
            return
    else:
        members = [dict(r) for r in conn.execute(
            "SELECT * FROM members WHERE status = 'active'"
        ).fetchall()]

    results = []
    for m in members:
        snapshots = _get_snapshots(conn, m["id"], from_date, to_date)
        meetings = _get_meetings(conn, m["id"], from_date, to_date)
        open_items = _get_open_items(conn, m["id"])
        flags = _get_flags(conn, m["id"])
        totals = _aggregate_metrics(snapshots)
        velocity = _compute_velocity(snapshots)
        momentum = _compute_momentum(snapshots)
        status = _member_status(snapshots, flags)
        avg_score = round(sum(s["score"] for s in snapshots) / len(snapshots), 1) if snapshots else 0
        avg_sentiment = (
            round(sum(mt.get("sentiment_score") or 0 for mt in meetings) / len(meetings), 2)
            if meetings else None
        )

        results.append({
            "member": m["name"],
            "member_id": m["id"],
            "github": m.get("github"),
            "title": m.get("title"),
            "status": status,
            "flags": flags,
            "period": {"from": from_date, "to": to_date},
            "snapshots_count": len(snapshots),
            "metrics": totals,
            "velocity": velocity,
            "momentum": momentum,
            "avg_score": avg_score,
            "meetings_count": len(meetings),
            "avg_sentiment": avg_sentiment,
            "open_items_count": len(open_items),
            "open_items": [{"kind": i["kind"], "content": i["content"]} for i in open_items],
        })

    conn.close()
    log_operation("report performance", args={"member": member_filter, "from": from_date, "to": to_date})

    if json_mode:
        data = results if len(results) != 1 else results[0]
        render_output(data, json_mode=True, copy=copy)
    else:
        parts = [f"# Performance Report — {from_date} to {to_date}\n"]
        for r in results:
            parts.append(f"## {r['member']}")
            if r["title"]:
                parts.append(f"*{r['title']}*")
            parts.append(f"**Status:** {r['status']}")
            if r["flags"]:
                parts.append(f"**Flags:** {', '.join(r['flags'])}")
            parts.append("")
            parts.append("### Activity")
            parts.append(f"- Commits: {r['metrics']['commits_count']}")
            parts.append(f"- PRs opened: {r['metrics']['prs_opened']}")
            parts.append(f"- PRs merged: {r['metrics']['prs_merged']}")
            parts.append(f"- Issues completed: {r['metrics']['issues_completed']}")
            parts.append(f"- Issues in progress: {r['metrics']['issues_in_progress']}")
            parts.append("")
            parts.append("### Performance")
            parts.append(f"- Avg score: {r['avg_score']}")
            parts.append(f"- Velocity (weekly): {r['velocity']}")
            parts.append(f"- Momentum (4w delta): {r['momentum']}")
            parts.append(f"- Snapshots: {r['snapshots_count']}")
            parts.append("")
            parts.append("### Meetings")
            parts.append(f"- Count: {r['meetings_count']}")
            if r["avg_sentiment"] is not None:
                parts.append(f"- Avg sentiment: {r['avg_sentiment']}")
            parts.append(f"- Open action items: {r['open_items_count']}")
            if r["open_items"]:
                for item in r["open_items"][:5]:
                    parts.append(f"  - [{item['kind']}] {item['content']}")
            parts.append("")
            parts.append("---")
        parts.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        render_output("\n".join(parts), copy=copy)


# ---- Report: Team ----

def cmd_report_team(args: argparse.Namespace) -> None:
    """Team health report."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    copy = getattr(args, "copy", False)
    team_name = getattr(args, "team", None)
    from_date, to_date = _date_range(args)

    if team_name:
        team, members = _get_team_members(conn, team_name)
        if not team:
            conn.close()
            render_output({"error": f"team '{team_name}' not found"}, json_mode=True)
            return
        team_label = team["name"]
    else:
        team = None
        members = [dict(r) for r in conn.execute(
            "SELECT * FROM members WHERE status = 'active'"
        ).fetchall()]
        team_label = "All Members"

    member_reports = []
    total_commits = 0
    total_prs_merged = 0
    total_issues = 0
    total_score = 0.0

    for m in members:
        snapshots = _get_snapshots(conn, m["id"], from_date, to_date)
        flags = _get_flags(conn, m["id"])
        totals = _aggregate_metrics(snapshots)
        velocity = _compute_velocity(snapshots)
        status = _member_status(snapshots, flags)
        avg_score = round(sum(s["score"] for s in snapshots) / len(snapshots), 1) if snapshots else 0
        member_reports.append({
            "member": m["name"],
            "status": status,
            "commits": totals["commits_count"],
            "prs_merged": totals["prs_merged"],
            "issues_completed": totals["issues_completed"],
            "velocity": velocity,
            "avg_score": avg_score,
            "snapshots": len(snapshots),
        })
        total_commits += totals["commits_count"]
        total_prs_merged += totals["prs_merged"]
        total_issues += totals["issues_completed"]
        total_score += avg_score

    team_avg_score = round(total_score / len(members), 1) if members else 0

    result = {
        "team": team_label,
        "period": {"from": from_date, "to": to_date},
        "member_count": len(members),
        "total_commits": total_commits,
        "total_prs_merged": total_prs_merged,
        "total_issues_completed": total_issues,
        "avg_score": team_avg_score,
        "members": member_reports,
    }

    conn.close()
    log_operation("report team", args={"team": team_name, "from": from_date, "to": to_date})

    if json_mode:
        render_output(result, json_mode=True, copy=copy)
    else:
        parts = [f"# Team Report — {team_label} — {from_date} to {to_date}\n"]
        parts.append(f"**Members:** {result['member_count']}")
        parts.append(f"**Total commits:** {result['total_commits']}")
        parts.append(f"**Total PRs merged:** {result['total_prs_merged']}")
        parts.append(f"**Total issues completed:** {result['total_issues_completed']}")
        parts.append(f"**Avg score:** {result['avg_score']}")
        parts.append("")
        headers = ["Member", "Status", "Commits", "PRs Merged", "Issues", "Velocity", "Avg Score"]
        rows = [
            [r["member"], r["status"], str(r["commits"]), str(r["prs_merged"]),
             str(r["issues_completed"]), str(r["velocity"]), str(r["avg_score"])]
            for r in member_reports
        ]
        parts.append(format_table(headers, rows))
        parts.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        render_output("\n".join(parts), copy=copy)


# ---- Report: Progress ----

def cmd_report_progress(args: argparse.Namespace) -> None:
    """Project progress report (snapshot trends)."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    copy = getattr(args, "copy", False)
    member_filter = getattr(args, "member", None)
    from_date, to_date = _date_range(args)

    if member_filter:
        m = _resolve_member(member_filter, conn)
        if not m:
            conn.close()
            render_output({"error": f"member '{member_filter}' not found"}, json_mode=True)
            return
        members = [m]
    else:
        members = [dict(r) for r in conn.execute(
            "SELECT * FROM members WHERE status = 'active'"
        ).fetchall()]

    daily_data: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total_score": 0.0, "count": 0, "members": {}}
    )
    for m in members:
        snapshots = _get_snapshots(conn, m["id"], from_date, to_date)
        for s in snapshots:
            d = daily_data[s["date"]]
            d["total_score"] += s.get("score", 0) or 0
            d["count"] += 1
            d["members"][m["name"]] = s.get("score", 0) or 0

    trend = []
    for date in sorted(daily_data.keys()):
        d = daily_data[date]
        avg = round(d["total_score"] / d["count"], 1) if d["count"] else 0
        trend.append({
            "date": date,
            "avg_score": avg,
            "total_score": round(d["total_score"], 1),
            "snapshots": d["count"],
            "members": d["members"],
        })

    result = {
        "period": {"from": from_date, "to": to_date},
        "member_filter": member_filter,
        "days_with_data": len(trend),
        "trend": trend,
    }

    conn.close()
    log_operation("report progress", args={"member": member_filter, "from": from_date, "to": to_date})

    if json_mode:
        render_output(result, json_mode=True, copy=copy)
    else:
        parts = [f"# Progress Report — {from_date} to {to_date}\n"]
        if member_filter:
            parts.append(f"**Member:** {member_filter}")
        parts.append(f"**Days with data:** {result['days_with_data']}")
        parts.append("")
        if trend:
            headers = ["Date", "Avg Score", "Total Score", "Snapshots"]
            rows = [
                [t["date"], str(t["avg_score"]), str(t["total_score"]), str(t["snapshots"])]
                for t in trend
            ]
            parts.append(format_table(headers, rows))
        else:
            parts.append("No snapshot data found for this period.")
        parts.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        render_output("\n".join(parts), copy=copy)


# ---- Report: Git ----

def cmd_report_git(args: argparse.Namespace) -> None:
    """Git analytics report."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    copy = getattr(args, "copy", False)
    member_filter = getattr(args, "member", None)
    from_date, to_date = _date_range(args)

    if member_filter:
        m = _resolve_member(member_filter, conn)
        if not m:
            conn.close()
            render_output({"error": f"member '{member_filter}' not found"}, json_mode=True)
            return
        members = [m]
    else:
        members = [dict(r) for r in conn.execute(
            "SELECT * FROM members WHERE status = 'active' AND github IS NOT NULL"
        ).fetchall()]

    results = []
    for m in members:
        snapshots = _get_snapshots(conn, m["id"], from_date, to_date)
        totals = _aggregate_metrics(snapshots)
        velocity = _compute_velocity(snapshots)
        momentum = _compute_momentum(snapshots)
        results.append({
            "member": m["name"],
            "github": m.get("github"),
            "commits": totals["commits_count"],
            "prs_opened": totals["prs_opened"],
            "prs_merged": totals["prs_merged"],
            "velocity": velocity,
            "momentum": momentum,
            "snapshots": len(snapshots),
        })

    conn.close()
    log_operation("report git", args={"member": member_filter, "from": from_date, "to": to_date})

    if json_mode:
        render_output(results, json_mode=True, copy=copy)
    else:
        parts = [f"# Git Report — {from_date} to {to_date}\n"]
        if member_filter:
            parts.append(f"**Member:** {member_filter}")
        parts.append("")
        if results:
            headers = ["Member", "GitHub", "Commits", "PRs Opened", "PRs Merged", "Velocity", "Momentum"]
            rows = [
                [r["member"], r.get("github") or "", str(r["commits"]),
                 str(r["prs_opened"]), str(r["prs_merged"]),
                 str(r["velocity"]), str(r["momentum"])]
                for r in results
            ]
            parts.append(format_table(headers, rows))
        else:
            parts.append("No members with GitHub handles found.")
        parts.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        render_output("\n".join(parts), copy=copy)


# ---- Report: Dashboard ----

def cmd_report_dashboard(args: argparse.Namespace) -> None:
    """Org-wide dashboard."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    copy = getattr(args, "copy", False)
    from_date, to_date = _date_range(args)

    total_members = conn.execute(
        "SELECT COUNT(*) FROM members WHERE status = 'active'"
    ).fetchone()[0]
    total_teams = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]

    snapshot_rows = conn.execute(
        """SELECT m.name, ps.metrics, ps.score
           FROM performance_snapshots ps
           JOIN members m ON m.id = ps.member_id
           WHERE ps.date >= ? AND ps.date <= ?
           ORDER BY ps.date""",
        (from_date, to_date),
    ).fetchall()

    member_scores: dict[str, list[float]] = defaultdict(list)
    total_commits = 0
    total_prs = 0
    total_issues = 0
    for row in snapshot_rows:
        metrics = json.loads(row["metrics"]) if row["metrics"] else {}
        member_scores[row["name"]].append(row["score"] or 0)
        total_commits += metrics.get("commits_count", 0)
        total_prs += metrics.get("prs_merged", 0)
        total_issues += metrics.get("issues_completed", 0)

    meeting_count = conn.execute(
        "SELECT COUNT(*) FROM meetings WHERE date >= ? AND date <= ?",
        (from_date, to_date),
    ).fetchone()[0]

    open_items_count = conn.execute(
        "SELECT COUNT(*) FROM meeting_items WHERE status = 'open'"
    ).fetchone()[0]

    member_summaries = []
    for name, scores in sorted(member_scores.items(), key=lambda x: -sum(x[1]) / max(1, len(x[1]))):
        avg = round(sum(scores) / len(scores), 1) if scores else 0
        member_summaries.append({"member": name, "avg_score": avg, "snapshots": len(scores)})

    result = {
        "period": {"from": from_date, "to": to_date},
        "active_members": total_members,
        "teams": total_teams,
        "total_commits": total_commits,
        "total_prs_merged": total_prs,
        "total_issues_completed": total_issues,
        "meetings": meeting_count,
        "open_action_items": open_items_count,
        "member_rankings": member_summaries,
    }

    conn.close()
    log_operation("report dashboard", args={"from": from_date, "to": to_date})

    if json_mode:
        render_output(result, json_mode=True, copy=copy)
    else:
        parts = [f"# Dashboard — {from_date} to {to_date}\n"]
        parts.append(f"**Active Members:** {result['active_members']}")
        parts.append(f"**Teams:** {result['teams']}")
        parts.append(f"**Total Commits:** {result['total_commits']}")
        parts.append(f"**Total PRs Merged:** {result['total_prs_merged']}")
        parts.append(f"**Total Issues Completed:** {result['total_issues_completed']}")
        parts.append(f"**Meetings:** {result['meetings']}")
        parts.append(f"**Open Action Items:** {result['open_action_items']}")
        parts.append("")
        if member_summaries:
            parts.append("## Member Rankings")
            headers = ["Member", "Avg Score", "Snapshots"]
            rows = [
                [m["member"], str(m["avg_score"]), str(m["snapshots"])]
                for m in member_summaries
            ]
            parts.append(format_table(headers, rows))
        parts.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        render_output("\n".join(parts), copy=copy)


# ---- Report: Custom ----

def cmd_report_custom(args: argparse.Namespace) -> None:
    """Free-form AI report from available data."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    copy = getattr(args, "copy", False)
    prompt = args.prompt
    member_filter = getattr(args, "member", None)
    config = load_config()
    from_date, to_date = _date_range(args)

    context_parts = [f"Period: {from_date} to {to_date}\n"]

    if member_filter:
        m = _resolve_member(member_filter, conn)
        if not m:
            conn.close()
            render_output({"error": f"member '{member_filter}' not found"}, json_mode=True)
            return
        members = [m]
        context_parts.append(f"Focus member: {m['name']}")
    else:
        members = [dict(r) for r in conn.execute(
            "SELECT * FROM members WHERE status = 'active'"
        ).fetchall()]

    for m in members:
        snapshots = _get_snapshots(conn, m["id"], from_date, to_date)
        meetings = _get_meetings(conn, m["id"], from_date, to_date)
        open_items = _get_open_items(conn, m["id"])
        flags = _get_flags(conn, m["id"])
        totals = _aggregate_metrics(snapshots)
        context_parts.append(f"\n## {m['name']}")
        if m.get("title"):
            context_parts.append(f"Title: {m['title']}")
        if flags:
            context_parts.append(f"Flags: {', '.join(flags)}")
        context_parts.append(
            f"Commits: {totals['commits_count']}, PRs opened: {totals['prs_opened']}, "
            f"PRs merged: {totals['prs_merged']}, Issues completed: {totals['issues_completed']}"
        )
        if snapshots:
            avg_score = round(sum(s["score"] for s in snapshots) / len(snapshots), 1)
            context_parts.append(f"Avg score: {avg_score} ({len(snapshots)} snapshots)")
        context_parts.append(f"Meetings: {len(meetings)}")
        if meetings:
            for mtg in meetings[-3:]:
                if mtg.get("summary"):
                    context_parts.append(f"  Meeting {mtg['date']}: {mtg['summary'][:200]}")
        if open_items:
            context_parts.append(f"Open items ({len(open_items)}):")
            for item in open_items[:5]:
                context_parts.append(f"  - [{item['kind']}] {item['content']}")

    conn.close()
    context = "\n".join(context_parts)

    from ascend.summarizer import get_client
    client = get_client(config)
    if not client:
        if json_mode:
            render_output({"error": "LLM API key not configured", "context": context}, json_mode=True, copy=copy)
        else:
            render_output(f"Error: LLM API key not configured.\n\nContext data:\n{context}", copy=copy)
        log_operation("report custom", args={"prompt": prompt}, error="no API key")
        return

    system_prompt = (
        "You are an AI assistant for engineering managers. Generate a clear, actionable report "
        "based on the team data provided. Use markdown formatting. Be concise and data-driven. "
        "Highlight risks, wins, and recommended actions."
    )

    try:
        response = client.messages.create(
            model=config.model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": f"User request: {prompt}\n\nTeam data:\n{context}",
            }],
        )
        report_text = response.content[0].text
    except Exception as e:
        if json_mode:
            render_output({"error": str(e), "context": context}, json_mode=True, copy=copy)
        else:
            render_output(f"LLM error: {e}\n\nContext data:\n{context}", copy=copy)
        log_operation("report custom", args={"prompt": prompt}, error=str(e))
        return

    log_operation("report custom", args={"prompt": prompt}, result="success")

    if json_mode:
        render_output({"prompt": prompt, "report": report_text}, json_mode=True, copy=copy)
    else:
        render_output(report_text, copy=copy)
