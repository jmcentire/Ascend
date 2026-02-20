"""Coach commands — analyze, risks, STAR assessments, suggestions."""

from __future__ import annotations

import argparse
import json
import sqlite3
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


# ---- Coach: Analyze ----

def cmd_coach_analyze(args: argparse.Namespace) -> None:
    """Comprehensive member analysis (LLM-powered)."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    copy = getattr(args, "copy", False)
    config = load_config()

    m = _resolve_member(args.member, conn)
    if not m:
        conn.close()
        render_output({"error": f"member '{args.member}' not found"}, json_mode=True)
        return

    context = _gather_full_context(m, conn)
    conn.close()

    from ascend.summarizer import get_client
    client = get_client(config)

    if not client:
        if json_mode:
            render_output({"error": "LLM API key not configured", "context": context}, json_mode=True, copy=copy)
        else:
            render_output(f"Error: LLM API key not configured.\n\nContext data:\n{context}", copy=copy)
        log_operation("coach analyze", args={"member": args.member}, error="no API key")
        return

    system_prompt = (
        "You are a coaching advisor for engineering managers. Given comprehensive data about "
        "a team member, produce a detailed analysis covering:\n\n"
        "1. **Executive Summary** — Current standing, key observations\n"
        "2. **Performance Assessment** — Quantitative analysis of output metrics\n"
        "3. **Attention Required** — Risks, concerns, flags to watch\n"
        "4. **Strengths & Wins** — What's going well\n"
        "5. **Growth Areas** — Where they can improve\n"
        "6. **Recommended Actions** — Specific next steps for the manager\n\n"
        "Be data-driven but empathetic. Use markdown formatting."
    )

    try:
        response = client.messages.create(
            model=config.model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": f"Analyze this team member:\n\n{context}"}],
        )
        analysis = response.content[0].text
    except Exception as e:
        if json_mode:
            render_output({"error": str(e)}, json_mode=True, copy=copy)
        else:
            render_output(f"LLM error: {e}", copy=copy)
        log_operation("coach analyze", args={"member": args.member}, error=str(e))
        return

    log_operation("coach analyze", args={"member": args.member}, result="success")

    if json_mode:
        render_output({"member": m["name"], "analysis": analysis}, json_mode=True, copy=copy)
    else:
        render_output(analysis, copy=copy)


# ---- Coach: Risks ----

def cmd_coach_risks(args: argparse.Namespace) -> None:
    """Risk dashboard — algorithmic detection of flight, burnout, bus factor, underperformance."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    copy = getattr(args, "copy", False)

    members = [dict(r) for r in conn.execute(
        "SELECT * FROM members WHERE status = 'active'"
    ).fetchall()]

    risk_reports = []
    for m in members:
        risks = _compute_risks(m, conn)
        if risks["signals"]:
            risk_reports.append(risks)

    conn.close()
    log_operation("coach risks")

    # Sort by total risk score descending
    risk_reports.sort(key=lambda r: r["risk_score"], reverse=True)

    if json_mode:
        render_output(risk_reports, json_mode=True, copy=copy)
    else:
        if not risk_reports:
            render_output("# Risk Dashboard\n\nNo risk signals detected.")
            return

        parts = [f"# Risk Dashboard\n"]
        parts.append(f"**Members with risk signals:** {len(risk_reports)}\n")

        headers = ["Member", "Risk Score", "Signals"]
        rows_data = []
        for r in risk_reports:
            signals_str = ", ".join(r["signals"])
            rows_data.append([r["member"], str(r["risk_score"]), signals_str])
        parts.append(format_table(headers, rows_data))

        parts.append("")
        for r in risk_reports:
            parts.append(f"\n## {r['member']} (risk score: {r['risk_score']})")
            for signal in r["signals"]:
                parts.append(f"- {signal}")
            if r.get("details"):
                for k, v in r["details"].items():
                    parts.append(f"  {k}: {v}")

        parts.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        render_output("\n".join(parts), copy=copy)


# ---- Coach: STAR ----

def cmd_coach_star(args: argparse.Namespace) -> None:
    """Record a STAR behavioral assessment."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)

    m = _resolve_member(args.member, conn)
    if not m:
        conn.close()
        render_output({"error": f"member '{args.member}' not found"}, json_mode=True)
        return

    star = {
        "situation": args.situation,
        "task": args.task,
        "action": args.action,
        "result": args.result,
    }
    content = json.dumps(star)

    cursor = conn.execute(
        "INSERT INTO coaching_entries (member_id, kind, content) VALUES (?, 'star_assessment', ?)",
        (m["id"], content),
    )
    conn.commit()
    entry_id = cursor.lastrowid

    result = {
        "id": entry_id,
        "member": m["name"],
        "member_id": m["id"],
        "kind": "star_assessment",
        "star": star,
    }

    conn.close()
    log_operation("coach star", args={"member": args.member})

    if json_mode:
        render_output(result, json_mode=True)
    else:
        parts = [f"STAR assessment recorded for {m['name']} (#{entry_id})"]
        parts.append(f"  Situation: {args.situation}")
        parts.append(f"  Task: {args.task}")
        parts.append(f"  Action: {args.action}")
        parts.append(f"  Result: {args.result}")
        render_output("\n".join(parts))


# ---- Coach: Suggest ----

def cmd_coach_suggest(args: argparse.Namespace) -> None:
    """Coaching suggestions for next 1:1 (LLM-powered)."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    copy = getattr(args, "copy", False)
    config = load_config()

    m = _resolve_member(args.member, conn)
    if not m:
        conn.close()
        render_output({"error": f"member '{args.member}' not found"}, json_mode=True)
        return

    context = _gather_full_context(m, conn)

    # Also include coaching history
    entries = conn.execute(
        "SELECT kind, content, created_at FROM coaching_entries WHERE member_id = ? ORDER BY created_at DESC LIMIT 10",
        (m["id"],),
    ).fetchall()
    if entries:
        context += "\n\nCoaching history:"
        for e in entries:
            context += f"\n  [{e['kind']}] {e['created_at']}: {e['content'][:200]}"

    # Include risk signals
    risks = _compute_risks(m, conn)
    if risks["signals"]:
        context += f"\n\nRisk signals: {', '.join(risks['signals'])}"

    conn.close()

    from ascend.summarizer import get_client
    client = get_client(config)

    if not client:
        if json_mode:
            render_output({"error": "LLM API key not configured", "context": context}, json_mode=True, copy=copy)
        else:
            render_output(f"Error: LLM API key not configured.\n\nContext data:\n{context}", copy=copy)
        log_operation("coach suggest", args={"member": args.member}, error="no API key")
        return

    system_prompt = (
        "You are a coaching advisor for engineering managers preparing for a 1:1 meeting. "
        "Given data about a team member, generate specific coaching suggestions:\n\n"
        "1. **Topics to discuss** — prioritized by importance\n"
        "2. **Questions to ask** — open-ended, growth-oriented\n"
        "3. **Feedback to give** — specific, behavioral (STAR format when applicable)\n"
        "4. **Watch for** — signals to observe during the conversation\n"
        "5. **Follow-up actions** — what to do after the meeting\n\n"
        "Be specific and actionable. Use markdown."
    )

    try:
        response = client.messages.create(
            model=config.model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": f"Coaching suggestions for {m['name']}:\n\n{context}"}],
        )
        suggestions = response.content[0].text
    except Exception as e:
        if json_mode:
            render_output({"error": str(e)}, json_mode=True, copy=copy)
        else:
            render_output(f"LLM error: {e}", copy=copy)
        log_operation("coach suggest", args={"member": args.member}, error=str(e))
        return

    log_operation("coach suggest", args={"member": args.member}, result="success")

    if json_mode:
        render_output({"member": m["name"], "suggestions": suggestions}, json_mode=True, copy=copy)
    else:
        render_output(suggestions, copy=copy)


# ---- Risk Algorithm ----

def _compute_risks(member: dict, conn: sqlite3.Connection) -> dict[str, Any]:
    """Compute risk signals for a member. Returns dict with signals list and score."""
    signals: list[str] = []
    details: dict[str, Any] = {}
    risk_score = 0

    member_id = member["id"]
    now = datetime.now()
    thirty_days_ago = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    seven_days_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")

    # Get flags
    flags = [r["flag"] for r in conn.execute(
        "SELECT flag FROM member_flags WHERE member_id = ?", (member_id,)
    ).fetchall()]

    # Explicit flags
    if "flight_risk" in flags:
        signals.append("flight_risk flag set")
        risk_score += 30
    if "pip" in flags:
        signals.append("on PIP")
        risk_score += 20

    # Performance data (last 30 days)
    snapshots = conn.execute(
        """SELECT date, metrics, score FROM performance_snapshots
           WHERE member_id = ? AND date >= ? ORDER BY date""",
        (member_id, thirty_days_ago),
    ).fetchall()

    if snapshots:
        scores = [s["score"] or 0 for s in snapshots]
        avg_score = sum(scores) / len(scores)
        details["avg_score_30d"] = round(avg_score, 1)

        # Underperformance: low average score
        if avg_score < 3 and len(snapshots) >= 3:
            signals.append("underperformance: avg score < 3 over 30d")
            risk_score += 25

        # Declining trend
        if len(scores) >= 3:
            first_half = sum(scores[:len(scores) // 2]) / max(1, len(scores) // 2)
            second_half = sum(scores[len(scores) // 2:]) / max(1, len(scores) - len(scores) // 2)
            if first_half > 0 and second_half < first_half * 0.5:
                signals.append("declining performance: second half < 50% of first half")
                risk_score += 15

        # Potential burnout: very high output
        if avg_score > 40:
            signals.append("potential burnout: sustained high output (avg > 40)")
            risk_score += 10

        # Overwork: high issues_in_progress
        total_in_progress = 0
        for s in snapshots:
            m_data = json.loads(s["metrics"]) if s["metrics"] else {}
            total_in_progress += m_data.get("issues_in_progress", 0)
        avg_wip = total_in_progress / len(snapshots)
        if avg_wip > 5:
            signals.append(f"high WIP: avg {avg_wip:.1f} issues in progress")
            risk_score += 10
            details["avg_wip"] = round(avg_wip, 1)
    else:
        # No snapshot data is itself a concern
        signals.append("no performance data in last 30 days")
        risk_score += 10

    # Meeting freshness
    last_meeting = conn.execute(
        "SELECT date FROM meetings WHERE member_id = ? ORDER BY date DESC LIMIT 1",
        (member_id,),
    ).fetchone()
    if last_meeting:
        last_date = last_meeting["date"]
        details["last_meeting"] = last_date
        if last_date < thirty_days_ago:
            signals.append(f"stale 1:1: last meeting was {last_date}")
            risk_score += 15
    else:
        signals.append("no 1:1 meetings on record")
        risk_score += 10

    # Sentiment trend
    recent_meetings = conn.execute(
        """SELECT sentiment_score FROM meetings
           WHERE member_id = ? AND date >= ? AND sentiment_score IS NOT NULL
           ORDER BY date""",
        (member_id, thirty_days_ago),
    ).fetchall()
    if len(recent_meetings) >= 2:
        sentiments = [r["sentiment_score"] for r in recent_meetings]
        avg_sentiment = sum(sentiments) / len(sentiments)
        details["avg_sentiment_30d"] = round(avg_sentiment, 2)
        if avg_sentiment < 0.4:
            signals.append(f"low meeting sentiment: avg {avg_sentiment:.2f}")
            risk_score += 15
        if len(sentiments) >= 3 and sentiments[-1] < sentiments[0] - 0.2:
            signals.append("declining sentiment trend")
            risk_score += 10

    # Open items overload
    open_items_count = conn.execute(
        """SELECT COUNT(*) FROM meeting_items mi
           JOIN meetings m ON m.id = mi.meeting_id
           WHERE m.member_id = ? AND mi.status = 'open'""",
        (member_id,),
    ).fetchone()[0]
    if open_items_count > 10:
        signals.append(f"action item overload: {open_items_count} open items")
        risk_score += 10
        details["open_items"] = open_items_count

    # Bus factor: sole contributor (only person with snapshots in their team)
    if member.get("team_id"):
        team_members_with_data = conn.execute(
            """SELECT COUNT(DISTINCT ps.member_id)
               FROM performance_snapshots ps
               JOIN team_members tm ON tm.member_id = ps.member_id
               WHERE tm.team_id = ? AND ps.date >= ?""",
            (member["team_id"], thirty_days_ago),
        ).fetchone()[0]
        if team_members_with_data == 1:
            signals.append("bus factor: sole contributor with data on team")
            risk_score += 15

    # Cap at 100
    risk_score = min(risk_score, 100)

    return {
        "member": member["name"],
        "member_id": member_id,
        "risk_score": risk_score,
        "signals": signals,
        "details": details,
    }


# ---- Context Gathering ----

def _gather_full_context(member: dict, conn: sqlite3.Connection) -> str:
    """Gather comprehensive context about a member for LLM prompts."""
    parts = [f"Member: {member['name']}"]
    if member.get("title"):
        parts.append(f"Title: {member['title']}")
    if member.get("github"):
        parts.append(f"GitHub: {member['github']}")
    if member.get("email"):
        parts.append(f"Email: {member['email']}")

    # Flags
    flags = [r["flag"] for r in conn.execute(
        "SELECT flag FROM member_flags WHERE member_id = ?", (member["id"],)
    ).fetchall()]
    if flags:
        parts.append(f"Flags: {', '.join(flags)}")

    # Performance snapshots
    snapshots = conn.execute(
        """SELECT date, metrics, score FROM performance_snapshots
           WHERE member_id = ? ORDER BY date DESC LIMIT 10""",
        (member["id"],),
    ).fetchall()
    if snapshots:
        parts.append("\nPerformance snapshots:")
        for s in snapshots:
            metrics = json.loads(s["metrics"]) if s["metrics"] else {}
            parts.append(
                f"  {s['date']}: score={s['score']}, "
                f"commits={metrics.get('commits_count', 0)}, "
                f"prs={metrics.get('prs_merged', 0)}, "
                f"issues={metrics.get('issues_completed', 0)}"
            )

    # Meetings
    meetings = conn.execute(
        """SELECT date, summary, sentiment_score FROM meetings
           WHERE member_id = ? ORDER BY date DESC LIMIT 5""",
        (member["id"],),
    ).fetchall()
    if meetings:
        parts.append("\nRecent meetings:")
        for mtg in meetings:
            parts.append(f"  {mtg['date']} (sentiment: {mtg['sentiment_score'] or '?'})")
            if mtg["summary"]:
                parts.append(f"    {mtg['summary'][:300]}")

    # Open items
    items = conn.execute(
        """SELECT mi.kind, mi.content FROM meeting_items mi
           JOIN meetings m ON m.id = mi.meeting_id
           WHERE m.member_id = ? AND mi.status = 'open'
           ORDER BY mi.created_at DESC LIMIT 10""",
        (member["id"],),
    ).fetchall()
    if items:
        parts.append("\nOpen action items:")
        for item in items:
            parts.append(f"  - [{item['kind']}] {item['content']}")

    # Goals
    goals = conn.execute(
        "SELECT type, title, current_value, target_value, status FROM goals WHERE member_id = ? ORDER BY id",
        (member["id"],),
    ).fetchall()
    if goals:
        parts.append("\nGoals:")
        for g in goals:
            progress = ""
            if g["target_value"]:
                progress = f" ({g['current_value'] or 0}/{g['target_value']})"
            parts.append(f"  - [{g['type']}] {g['title']}{progress} [{g['status']}]")

    # Coaching entries
    entries = conn.execute(
        "SELECT kind, content, created_at FROM coaching_entries WHERE member_id = ? ORDER BY created_at DESC LIMIT 5",
        (member["id"],),
    ).fetchall()
    if entries:
        parts.append("\nCoaching history:")
        for e in entries:
            parts.append(f"  [{e['kind']}] {e['created_at']}: {e['content'][:200]}")

    return "\n".join(parts)
