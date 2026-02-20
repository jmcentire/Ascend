"""Plan commands — goals, PIPs, career development."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from typing import Optional

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


def _current_cycle() -> str:
    """Derive current planning cycle from date (e.g., '2025-Q1')."""
    now = datetime.now()
    quarter = (now.month - 1) // 3 + 1
    return f"{now.year}-Q{quarter}"


# ---- Plan: Cycle ----

def cmd_plan_cycle(args: argparse.Namespace) -> None:
    """Show current planning cycle and goal summary."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    cycle = _current_cycle()

    goals = conn.execute(
        "SELECT * FROM goals WHERE cycle = ?", (cycle,)
    ).fetchall()

    by_type: dict[str, list[dict]] = {}
    for g in goals:
        gd = dict(g)
        by_type.setdefault(gd["type"], []).append(gd)

    active = sum(1 for g in goals if g["status"] == "active")
    completed = sum(1 for g in goals if g["status"] == "completed")

    result = {
        "cycle": cycle,
        "total_goals": len(goals),
        "active": active,
        "completed": completed,
        "by_type": {k: len(v) for k, v in by_type.items()},
    }

    conn.close()
    log_operation("plan cycle")

    if json_mode:
        render_output(result, json_mode=True)
    else:
        parts = [f"# Planning Cycle: {cycle}\n"]
        parts.append(f"**Total goals:** {len(goals)}")
        parts.append(f"**Active:** {active}")
        parts.append(f"**Completed:** {completed}")
        if by_type:
            parts.append("")
            for t, gs in by_type.items():
                parts.append(f"- {t}: {len(gs)}")
        else:
            parts.append("\nNo goals set for this cycle.")
        render_output("\n".join(parts))


# ---- Plan: Goal Create ----

def cmd_plan_goal_create(args: argparse.Namespace) -> None:
    """Create a goal (objective, key_result, pip_criterion, career_milestone)."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)

    member_id = None
    team_id = None

    if args.member:
        m = _resolve_member(args.member, conn)
        if not m:
            conn.close()
            render_output({"error": f"member '{args.member}' not found"}, json_mode=True)
            return
        member_id = m["id"]

    if args.team:
        if args.team.isdigit():
            team_row = conn.execute("SELECT id FROM teams WHERE id = ?", (int(args.team),)).fetchone()
        else:
            team_row = conn.execute(
                "SELECT id FROM teams WHERE LOWER(name) = LOWER(?)", (args.team,)
            ).fetchone()
        if not team_row:
            conn.close()
            render_output({"error": f"team '{args.team}' not found"}, json_mode=True)
            return
        team_id = team_row["id"]

    cycle = args.cycle or _current_cycle()
    goal_type = args.type
    target = args.target

    cursor = conn.execute(
        """INSERT INTO goals (member_id, team_id, cycle, type, title, description, target_value, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'active')""",
        (member_id, team_id, cycle, goal_type, args.title, args.description, target),
    )
    conn.commit()
    goal_id = cursor.lastrowid

    result = {
        "id": goal_id,
        "member_id": member_id,
        "team_id": team_id,
        "cycle": cycle,
        "type": goal_type,
        "title": args.title,
        "description": args.description,
        "target_value": target,
        "status": "active",
    }

    conn.close()
    log_operation("plan goal create", args={"title": args.title, "type": goal_type})

    if json_mode:
        render_output(result, json_mode=True)
    else:
        render_output(f"Goal #{goal_id} created: [{goal_type}] {args.title}")


# ---- Plan: Goal List ----

def cmd_plan_goal_list(args: argparse.Namespace) -> None:
    """List goals with filters."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)

    query = "SELECT g.*, m.name as member_name FROM goals g LEFT JOIN members m ON m.id = g.member_id WHERE 1=1"
    params: list = []

    cycle = getattr(args, "cycle", None) or _current_cycle()
    query += " AND g.cycle = ?"
    params.append(cycle)

    status = getattr(args, "status", None)
    if status and status != "all":
        query += " AND g.status = ?"
        params.append(status)

    member_filter = getattr(args, "member", None)
    if member_filter:
        m = _resolve_member(member_filter, conn)
        if not m:
            conn.close()
            render_output({"error": f"member '{member_filter}' not found"}, json_mode=True)
            return
        query += " AND g.member_id = ?"
        params.append(m["id"])

    goal_type = getattr(args, "type", None)
    if goal_type:
        query += " AND g.type = ?"
        params.append(goal_type)

    query += " ORDER BY g.id"
    rows = conn.execute(query, params).fetchall()
    goals = [dict(r) for r in rows]

    conn.close()
    log_operation("plan goal list", args={"cycle": cycle, "status": status})

    if json_mode:
        render_output(goals, json_mode=True)
    else:
        if not goals:
            render_output(f"No goals found for cycle {cycle}.")
            return
        parts = [f"# Goals — {cycle}\n"]
        headers = ["ID", "Type", "Member", "Title", "Progress", "Status"]
        rows_data = []
        for g in goals:
            progress = ""
            if g["target_value"] and g["target_value"] > 0:
                pct = (g["current_value"] or 0) / g["target_value"] * 100
                progress = f"{g['current_value'] or 0}/{g['target_value']} ({pct:.0f}%)"
            rows_data.append([
                str(g["id"]), g["type"], g.get("member_name") or "-",
                g["title"], progress, g["status"],
            ])
        parts.append(format_table(headers, rows_data))
        render_output("\n".join(parts))


# ---- Plan: Goal Update ----

def cmd_plan_goal_update(args: argparse.Namespace) -> None:
    """Update a goal's value or status."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    goal_id = args.id

    row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
    if not row:
        conn.close()
        render_output({"error": f"goal #{goal_id} not found"}, json_mode=True)
        return

    updates = []
    params: list = []
    if args.value is not None:
        updates.append("current_value = ?")
        params.append(args.value)
    if args.status:
        updates.append("status = ?")
        params.append(args.status)
    if args.title:
        updates.append("title = ?")
        params.append(args.title)

    if not updates:
        conn.close()
        render_output({"error": "no updates specified"}, json_mode=True)
        return

    updates.append("updated_at = datetime('now')")
    params.append(goal_id)
    conn.execute(f"UPDATE goals SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()

    updated = dict(conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone())
    conn.close()
    log_operation("plan goal update", args={"id": goal_id})

    if json_mode:
        render_output(updated, json_mode=True)
    else:
        render_output(f"Goal #{goal_id} updated: {updated['title']} [{updated['status']}]")


# ---- Plan: PIP Create ----

def cmd_plan_pip_create(args: argparse.Namespace) -> None:
    """Create a PIP for a member — sets flag and creates pip_criterion goals."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    config = load_config()

    m = _resolve_member(args.member, conn)
    if not m:
        conn.close()
        render_output({"error": f"member '{args.member}' not found"}, json_mode=True)
        return

    cycle = _current_cycle()
    criteria: list[dict] = []

    # If criteria provided via args, use them
    if args.criteria:
        for c in args.criteria:
            cursor = conn.execute(
                """INSERT INTO goals (member_id, cycle, type, title, target_value, status)
                   VALUES (?, ?, 'pip_criterion', ?, 1.0, 'active')""",
                (m["id"], cycle, c),
            )
            conn.commit()
            criteria.append({"id": cursor.lastrowid, "title": c})
    else:
        # Try LLM-assisted PIP creation
        context = _gather_member_context(m, conn)
        pip_criteria = _generate_pip_criteria(m["name"], context, config)
        if pip_criteria:
            for title in pip_criteria:
                cursor = conn.execute(
                    """INSERT INTO goals (member_id, cycle, type, title, target_value, status)
                       VALUES (?, ?, 'pip_criterion', ?, 1.0, 'active')""",
                    (m["id"], cycle, title),
                )
                conn.commit()
                criteria.append({"id": cursor.lastrowid, "title": title})

    # Set PIP flag
    conn.execute(
        "INSERT OR IGNORE INTO member_flags (member_id, flag) VALUES (?, 'pip')",
        (m["id"],),
    )
    conn.commit()

    result = {
        "member": m["name"],
        "member_id": m["id"],
        "cycle": cycle,
        "criteria": criteria,
        "flag_set": True,
    }

    conn.close()
    log_operation("plan pip create", args={"member": args.member})

    if json_mode:
        render_output(result, json_mode=True)
    else:
        parts = [f"PIP created for {m['name']} (cycle: {cycle})"]
        if criteria:
            parts.append(f"{len(criteria)} criteria:")
            for c in criteria:
                parts.append(f"  #{c['id']}: {c['title']}")
        else:
            parts.append("No criteria generated. Add manually with: ascend plan goal create --member ... --type pip_criterion")
        parts.append("Flag 'pip' set.")
        render_output("\n".join(parts))


# ---- Plan: PIP Show ----

def cmd_plan_pip_show(args: argparse.Namespace) -> None:
    """Show PIP status for a member."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)

    m = _resolve_member(args.member, conn)
    if not m:
        conn.close()
        render_output({"error": f"member '{args.member}' not found"}, json_mode=True)
        return

    # Check PIP flag
    has_pip = conn.execute(
        "SELECT 1 FROM member_flags WHERE member_id = ? AND flag = 'pip'", (m["id"],)
    ).fetchone() is not None

    # Get PIP criteria
    criteria = [dict(r) for r in conn.execute(
        """SELECT * FROM goals WHERE member_id = ? AND type = 'pip_criterion'
           ORDER BY id""",
        (m["id"],),
    ).fetchall()]

    active = sum(1 for c in criteria if c["status"] == "active")
    completed = sum(1 for c in criteria if c["status"] == "completed")

    result = {
        "member": m["name"],
        "member_id": m["id"],
        "pip_flag": has_pip,
        "criteria_count": len(criteria),
        "active": active,
        "completed": completed,
        "criteria": criteria,
    }

    conn.close()
    log_operation("plan pip show", args={"member": args.member})

    if json_mode:
        render_output(result, json_mode=True)
    else:
        parts = [f"# PIP Status — {m['name']}\n"]
        parts.append(f"**PIP Flag:** {'Yes' if has_pip else 'No'}")
        parts.append(f"**Criteria:** {len(criteria)} ({active} active, {completed} completed)")
        parts.append("")
        if criteria:
            headers = ["ID", "Criterion", "Progress", "Status"]
            rows_data = []
            for c in criteria:
                progress = f"{c['current_value'] or 0}/{c['target_value'] or 1}"
                rows_data.append([str(c["id"]), c["title"], progress, c["status"]])
            parts.append(format_table(headers, rows_data))
        else:
            parts.append("No PIP criteria found.")
        render_output("\n".join(parts))


# ---- Plan: Career ----

def cmd_plan_career(args: argparse.Namespace) -> None:
    """Career development plan for a member (LLM-assisted)."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    copy = getattr(args, "copy", False)
    config = load_config()

    m = _resolve_member(args.member, conn)
    if not m:
        conn.close()
        render_output({"error": f"member '{args.member}' not found"}, json_mode=True)
        return

    context = _gather_member_context(m, conn)

    # Get existing career milestones
    milestones = [dict(r) for r in conn.execute(
        "SELECT * FROM goals WHERE member_id = ? AND type = 'career_milestone' ORDER BY id",
        (m["id"],),
    ).fetchall()]

    conn.close()

    # Try LLM
    from ascend.summarizer import get_client
    client = get_client(config)

    if not client:
        result = {
            "member": m["name"],
            "milestones": milestones,
            "plan": None,
            "error": "LLM API key not configured",
        }
        if json_mode:
            render_output(result, json_mode=True, copy=copy)
        else:
            parts = [f"# Career Plan — {m['name']}\n"]
            parts.append("Error: LLM API key not configured.")
            if milestones:
                parts.append(f"\n## Existing Milestones ({len(milestones)})")
                for ms in milestones:
                    parts.append(f"- {ms['title']} [{ms['status']}]")
            render_output("\n".join(parts), copy=copy)
        log_operation("plan career", args={"member": args.member}, error="no API key")
        return

    system_prompt = (
        "You are a career development advisor for engineering managers. Given context about "
        "a team member — their role, performance data, meeting notes, and current milestones — "
        "generate a thoughtful career development plan. Include:\n"
        "1. Current assessment (strengths, growth areas)\n"
        "2. Recommended growth trajectory (6-12 month horizon)\n"
        "3. Specific milestones to set\n"
        "4. Skills to develop\n"
        "5. Suggested conversations/topics for 1:1s\n"
        "Use markdown formatting."
    )

    try:
        response = client.messages.create(
            model=config.model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": context}],
        )
        plan_text = response.content[0].text
    except Exception as e:
        if json_mode:
            render_output({"error": str(e), "member": m["name"]}, json_mode=True, copy=copy)
        else:
            render_output(f"LLM error: {e}", copy=copy)
        log_operation("plan career", args={"member": args.member}, error=str(e))
        return

    log_operation("plan career", args={"member": args.member}, result="success")

    if json_mode:
        render_output({
            "member": m["name"],
            "milestones": milestones,
            "plan": plan_text,
        }, json_mode=True, copy=copy)
    else:
        render_output(plan_text, copy=copy)


# ---- Helpers ----

def _gather_member_context(member: dict, conn: sqlite3.Connection) -> str:
    """Gather all available context about a member for LLM prompts."""
    parts = [f"Member: {member['name']}"]
    if member.get("title"):
        parts.append(f"Title: {member['title']}")
    if member.get("github"):
        parts.append(f"GitHub: {member['github']}")

    # Flags
    flags = [r["flag"] for r in conn.execute(
        "SELECT flag FROM member_flags WHERE member_id = ?", (member["id"],)
    ).fetchall()]
    if flags:
        parts.append(f"Flags: {', '.join(flags)}")

    # Recent snapshots
    snapshots = conn.execute(
        """SELECT date, metrics, score FROM performance_snapshots
           WHERE member_id = ? ORDER BY date DESC LIMIT 5""",
        (member["id"],),
    ).fetchall()
    if snapshots:
        parts.append("\nRecent performance:")
        for s in snapshots:
            metrics = json.loads(s["metrics"]) if s["metrics"] else {}
            parts.append(
                f"  {s['date']}: score={s['score']}, commits={metrics.get('commits_count', 0)}, "
                f"prs_merged={metrics.get('prs_merged', 0)}, issues={metrics.get('issues_completed', 0)}"
            )

    # Recent meetings
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

    return "\n".join(parts)


def _generate_pip_criteria(member_name: str, context: str, config) -> list[str]:
    """Use LLM to generate PIP criteria. Returns list of criterion titles."""
    from ascend.summarizer import get_client
    client = get_client(config)
    if not client:
        return []

    system_prompt = (
        "You are an HR advisor helping create a Performance Improvement Plan (PIP). "
        "Given context about a team member, generate 3-5 specific, measurable PIP criteria. "
        "Return ONLY a JSON array of strings, each being a clear criterion title. "
        "Example: [\"Complete code reviews within 24 hours\", \"Ship 2 features per sprint\"]"
    )

    try:
        response = client.messages.create(
            model=config.model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": f"Create PIP criteria for {member_name}.\n\nContext:\n{context}",
            }],
        )
        from ascend.summarizer import _parse_json
        parsed = _parse_json(response.content[0].text)
        if isinstance(parsed, list):
            return [str(c) for c in parsed if c]
    except Exception:
        pass
    return []
