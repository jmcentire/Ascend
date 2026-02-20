"""Roster commands — list, add, edit, show, flag, unflag, search, import."""

from __future__ import annotations

import argparse
import csv
import re
import sqlite3
from pathlib import Path
from typing import Optional

from ascend.audit import log_operation
from ascend.config import DB_PATH, load_config
from ascend.db import get_connection
from ascend.models.member import Member
from ascend.output import format_table, render_output


def _get_conn() -> sqlite3.Connection:
    return get_connection(DB_PATH)


def _row_to_member(row: sqlite3.Row, conn: sqlite3.Connection) -> Member:
    """Convert a DB row to a Member model, including flags."""
    d = dict(row)
    flags = [
        r["flag"]
        for r in conn.execute(
            "SELECT flag FROM member_flags WHERE member_id = ?", (d["id"],)
        ).fetchall()
    ]
    d["flags"] = flags
    return Member(**d)


def _resolve_member(identifier: str, conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    """Find a member by name, github, email, or id."""
    if identifier.isdigit():
        return conn.execute("SELECT * FROM members WHERE id = ?", (int(identifier),)).fetchone()
    row = conn.execute("SELECT * FROM members WHERE github = ?", (identifier,)).fetchone()
    if row:
        return row
    row = conn.execute("SELECT * FROM members WHERE LOWER(name) = LOWER(?)", (identifier,)).fetchone()
    if row:
        return row
    row = conn.execute("SELECT * FROM members WHERE email LIKE ?", (f"%{identifier}%",)).fetchone()
    return row


def cmd_roster_list(args: argparse.Namespace) -> None:
    """List all members with optional filters."""
    conn = _get_conn()
    query = "SELECT * FROM members WHERE 1=1"
    params: list = []

    if getattr(args, "team", None):
        query += """ AND (team_id IN (SELECT id FROM teams WHERE LOWER(name) = LOWER(?))
                     OR id IN (SELECT member_id FROM team_members
                               JOIN teams ON teams.id = team_members.team_id
                               WHERE LOWER(teams.name) = LOWER(?)))"""
        params.extend([args.team, args.team])

    if getattr(args, "status", None):
        query += " AND status = ?"
        params.append(args.status)

    if getattr(args, "flag", None):
        query += " AND id IN (SELECT member_id FROM member_flags WHERE flag = ?)"
        params.append(args.flag)

    query += " ORDER BY name"
    rows = conn.execute(query, params).fetchall()
    members = [_row_to_member(r, conn) for r in rows]
    conn.close()

    log_operation("roster list", args={"count": len(members)})

    if getattr(args, "json", False):
        render_output([m.model_dump() for m in members], json_mode=True)
    else:
        if not members:
            render_output("No members found.")
            return
        headers = ["ID", "Name", "GitHub", "Title", "Status", "Flags"]
        table_rows = [
            [str(m.id), m.name, m.github or "", m.title or "", m.status, ", ".join(m.flags)]
            for m in members
        ]
        render_output(format_table(headers, table_rows))


def cmd_roster_add(args: argparse.Namespace) -> None:
    """Add a new member."""
    conn = _get_conn()

    # Check for duplicate github
    if args.github:
        existing = conn.execute("SELECT id FROM members WHERE github = ?", (args.github,)).fetchone()
        if existing:
            conn.close()
            render_output(f"Error: member with github '{args.github}' already exists (id={existing['id']})")
            return

    conn.execute(
        """INSERT INTO members (name, email, github, slack, phone, title, team_id, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'active')""",
        (
            args.name,
            getattr(args, "email", None),
            getattr(args, "github", None),
            getattr(args, "slack", None),
            getattr(args, "phone", None),
            getattr(args, "title", None),
            getattr(args, "team", None),
        ),
    )
    conn.commit()
    member_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    log_operation("roster add", args={"name": args.name, "id": member_id})

    if getattr(args, "json", False):
        render_output({"id": member_id, "name": args.name}, json_mode=True)
    else:
        render_output(f"Added member: {args.name} (id={member_id})")


def cmd_roster_edit(args: argparse.Namespace) -> None:
    """Edit an existing member."""
    conn = _get_conn()
    row = _resolve_member(args.member, conn)
    if not row:
        conn.close()
        render_output(f"Error: member '{args.member}' not found")
        return

    fields = ["name", "email", "personal_email", "github", "slack", "phone", "title", "status"]
    updates = []
    params = []
    for field in fields:
        value = getattr(args, field, None)
        if value is not None:
            updates.append(f"{field} = ?")
            params.append(value)

    if getattr(args, "team", None):
        updates.append("team_id = ?")
        # Resolve team by name or id
        team_val = args.team
        if team_val.isdigit():
            params.append(int(team_val))
        else:
            team_row = conn.execute("SELECT id FROM teams WHERE LOWER(name) = LOWER(?)", (team_val,)).fetchone()
            if team_row:
                params.append(team_row["id"])
            else:
                conn.close()
                render_output(f"Error: team '{team_val}' not found")
                return

    if not updates:
        conn.close()
        render_output("No fields to update. Use --name, --email, --github, etc.")
        return

    updates.append("updated_at = datetime('now')")
    params.append(row["id"])
    conn.execute(f"UPDATE members SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()

    log_operation("roster edit", args={"member": args.member, "fields": len(updates) - 1})
    render_output(f"Updated member: {row['name']}", json_mode=getattr(args, "json", False))


def cmd_roster_show(args: argparse.Namespace) -> None:
    """Show full member profile."""
    conn = _get_conn()
    row = _resolve_member(args.member, conn)
    if not row:
        conn.close()
        render_output(f"Error: member '{args.member}' not found")
        return

    member = _row_to_member(row, conn)

    # Get team info
    team_name = None
    if member.team_id:
        team_row = conn.execute("SELECT name FROM teams WHERE id = ?", (member.team_id,)).fetchone()
        if team_row:
            team_name = team_row["name"]

    # Get additional teams via team_members
    extra_teams = conn.execute(
        """SELECT t.name, tm.role FROM team_members tm
           JOIN teams t ON t.id = tm.team_id
           WHERE tm.member_id = ?""",
        (member.id,),
    ).fetchall()

    # Recent meetings
    meetings = conn.execute(
        "SELECT id, date, source, summary FROM meetings WHERE member_id = ? ORDER BY date DESC LIMIT 5",
        (member.id,),
    ).fetchall()

    # Open action items
    items = conn.execute(
        """SELECT mi.content, mi.kind FROM meeting_items mi
           JOIN meetings m ON m.id = mi.meeting_id
           WHERE m.member_id = ? AND mi.status = 'open'
           ORDER BY mi.created_at DESC LIMIT 10""",
        (member.id,),
    ).fetchall()

    conn.close()

    log_operation("roster show", args={"member": args.member})

    if getattr(args, "json", False):
        data = member.model_dump()
        data["team_name"] = team_name
        data["extra_teams"] = [{"name": t["name"], "role": t["role"]} for t in extra_teams]
        data["recent_meetings"] = [dict(m) for m in meetings]
        data["open_items"] = [{"content": i["content"], "kind": i["kind"]} for i in items]
        render_output(data, json_mode=True)
    else:
        lines = [f"## {member.name}\n"]
        if member.title:
            lines.append(f"**Title:** {member.title}")
        if member.email:
            lines.append(f"**Email:** {member.email}")
        if member.github:
            lines.append(f"**GitHub:** @{member.github}")
        if member.slack:
            lines.append(f"**Slack:** {member.slack}")
        if member.phone:
            lines.append(f"**Phone:** {member.phone}")
        lines.append(f"**Status:** {member.status}")
        if team_name:
            lines.append(f"**Team:** {team_name}")
        if extra_teams:
            for t in extra_teams:
                lines.append(f"**Also:** {t['name']} ({t['role']})")
        if member.flags:
            lines.append(f"**Flags:** {', '.join(member.flags)}")

        if meetings:
            lines.append("\n### Recent Meetings\n")
            for m in meetings:
                summary = m["summary"] or "(no summary)"
                lines.append(f"- {m['date']}: {summary[:80]}")

        if items:
            lines.append("\n### Open Items\n")
            for i in items:
                lines.append(f"- [{i['kind']}] {i['content']}")

        render_output("\n".join(lines), copy=getattr(args, "copy", False))


def cmd_roster_flag(args: argparse.Namespace) -> None:
    """Set a flag on a member."""
    conn = _get_conn()
    row = _resolve_member(args.member, conn)
    if not row:
        conn.close()
        render_output(f"Error: member '{args.member}' not found")
        return

    try:
        conn.execute(
            "INSERT INTO member_flags (member_id, flag) VALUES (?, ?)",
            (row["id"], args.flag),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # Already flagged

    conn.close()
    log_operation("roster flag", args={"member": args.member, "flag": args.flag})
    render_output(f"Flagged {row['name']} as '{args.flag}'", json_mode=getattr(args, "json", False))


def cmd_roster_unflag(args: argparse.Namespace) -> None:
    """Remove a flag from a member."""
    conn = _get_conn()
    row = _resolve_member(args.member, conn)
    if not row:
        conn.close()
        render_output(f"Error: member '{args.member}' not found")
        return

    conn.execute(
        "DELETE FROM member_flags WHERE member_id = ? AND flag = ?",
        (row["id"], args.flag),
    )
    conn.commit()
    conn.close()
    log_operation("roster unflag", args={"member": args.member, "flag": args.flag})
    render_output(f"Removed '{args.flag}' from {row['name']}", json_mode=getattr(args, "json", False))


def cmd_roster_search(args: argparse.Namespace) -> None:
    """Search members by name, email, github, title, or flags."""
    conn = _get_conn()
    q = f"%{args.query}%"
    rows = conn.execute(
        """SELECT DISTINCT m.* FROM members m
           LEFT JOIN member_flags mf ON mf.member_id = m.id
           WHERE m.name LIKE ? OR m.email LIKE ? OR m.github LIKE ?
              OR m.title LIKE ? OR m.slack LIKE ? OR mf.flag LIKE ?
           ORDER BY m.name""",
        (q, q, q, q, q, q),
    ).fetchall()
    members = [_row_to_member(r, conn) for r in rows]
    conn.close()

    log_operation("roster search", args={"query": args.query, "results": len(members)})

    if getattr(args, "json", False):
        render_output([m.model_dump() for m in members], json_mode=True)
    else:
        if not members:
            render_output(f"No members matching '{args.query}'")
            return
        headers = ["ID", "Name", "GitHub", "Title", "Flags"]
        table_rows = [
            [str(m.id), m.name, m.github or "", m.title or "", ", ".join(m.flags)]
            for m in members
        ]
        render_output(format_table(headers, table_rows))


def cmd_roster_import(args: argparse.Namespace) -> None:
    """Import members from CSV or team-tracker directory."""
    path = Path(args.file)
    if not path.exists():
        render_output(f"Error: path '{path}' not found")
        return

    conn = _get_conn()
    imported = 0
    skipped = 0

    if path.is_file() and path.suffix == ".csv":
        imported, skipped = _import_csv(path, conn)
    elif path.is_dir():
        imported, skipped = _import_team_tracker(path, conn)
    else:
        conn.close()
        render_output(f"Error: unsupported file type '{path.suffix}'. Use .csv or a team-tracker directory.")
        return

    conn.close()
    log_operation("roster import", args={"file": str(path), "imported": imported, "skipped": skipped})

    if getattr(args, "json", False):
        render_output({"imported": imported, "skipped": skipped, "source": str(path)}, json_mode=True)
    else:
        render_output(f"Imported {imported} members ({skipped} skipped) from {path}")


def _import_csv(path: Path, conn: sqlite3.Connection) -> tuple[int, int]:
    """Import from CSV format: name, email_full, slack, github."""
    imported = 0
    skipped = 0

    with open(path) as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 4:
                continue
            name, email_full, slack, github = row[0].strip(), row[1].strip(), row[2].strip(), row[3].strip()

            if not name:
                continue

            # Extract email from "Name <email>" format
            email_match = re.search(r"<(.+?)>", email_full)
            email = email_match.group(1) if email_match else email_full

            # Clean slack handle
            slack = slack.lstrip("@")

            # Check for existing
            existing = conn.execute("SELECT id FROM members WHERE github = ?", (github,)).fetchone()
            if existing:
                skipped += 1
                continue

            conn.execute(
                """INSERT INTO members (name, email, github, slack, status)
                   VALUES (?, ?, ?, ?, 'active')""",
                (name, email, github, slack),
            )
            imported += 1

    conn.commit()
    return imported, skipped


def _import_team_tracker(path: Path, conn: sqlite3.Connection) -> tuple[int, int]:
    """Import from team-tracker/members/ directory structure."""
    imported = 0
    skipped = 0

    for member_dir in sorted(path.iterdir()):
        if not member_dir.is_dir():
            continue

        github = member_dir.name
        profile_path = member_dir / "profile.md"
        if not profile_path.exists():
            continue

        # Parse profile.md
        content = profile_path.read_text()
        name = _extract_md_heading(content) or github
        email = _extract_md_field(content, "Email")
        slack = _extract_md_field(content, "Slack")
        if slack:
            slack = slack.lstrip("@")

        # Extract role/title
        title = _extract_md_section_first_line(content, "Role")

        # Extract status
        status = "active"
        if "- [x] On improvement plan" in content:
            status = "pip"
        elif "- [x] Needs attention" in content:
            status = "needs_attention"

        # Check for existing — merge if found
        existing = conn.execute("SELECT id FROM members WHERE github = ?", (github,)).fetchone()
        if existing:
            # Enrich existing record with profile data
            updates = []
            params = []
            if title:
                updates.append("title = ?")
                params.append(title)
            if email and not conn.execute("SELECT email FROM members WHERE id = ? AND email IS NOT NULL", (existing["id"],)).fetchone():
                updates.append("email = ?")
                params.append(email)
            if status != "active":
                updates.append("status = ?")
                params.append(status)
            if updates:
                updates.append("updated_at = datetime('now')")
                params.append(existing["id"])
                conn.execute(f"UPDATE members SET {', '.join(updates)} WHERE id = ?", params)
                imported += 1
            else:
                skipped += 1
            member_id = existing["id"]
        else:
            conn.execute(
                """INSERT INTO members (name, email, github, slack, title, status)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (name, email, github, slack, title, status),
            )
            member_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            imported += 1

        # Import notes as coaching entry if substantive
        notes_path = member_dir / "notes.md"
        if notes_path.exists():
            notes_content = notes_path.read_text().strip()
            if len(notes_content) > 100:  # Only if there's real content
                # Avoid duplicates
                existing_entry = conn.execute(
                    "SELECT id FROM coaching_entries WHERE member_id = ? AND kind = 'observation' AND content = ?",
                    (member_id, notes_content),
                ).fetchone()
                if not existing_entry:
                    conn.execute(
                        """INSERT INTO coaching_entries (member_id, kind, content)
                           VALUES (?, 'observation', ?)""",
                        (member_id, notes_content),
                    )

    conn.commit()
    return imported, skipped


def _extract_md_heading(content: str) -> Optional[str]:
    """Extract the first # heading from markdown."""
    for line in content.split("\n"):
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _extract_md_field(content: str, field: str) -> Optional[str]:
    """Extract a **Field:** value from markdown."""
    pattern = rf"\*\*{field}:\*\*\s*(.+)"
    match = re.search(pattern, content)
    if match:
        return match.group(1).strip()
    return None


def _extract_md_section_first_line(content: str, section: str) -> Optional[str]:
    """Extract the first non-empty line after a ## Section heading."""
    lines = content.split("\n")
    in_section = False
    for line in lines:
        if line.strip().startswith(f"## {section}"):
            in_section = True
            continue
        if in_section:
            stripped = line.strip()
            if stripped.startswith("## "):
                break
            if stripped and not stripped.startswith("-"):
                return stripped
            if stripped.startswith("- "):
                return stripped[2:]
    return None
