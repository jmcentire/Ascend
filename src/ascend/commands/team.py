"""Team commands — list, create, add, show."""

from __future__ import annotations

import argparse
import sqlite3

from ascend.audit import log_operation
from ascend.config import DB_PATH
from ascend.db import get_connection
from ascend.models.member import Member, Team
from ascend.output import format_table, render_output


def _get_conn() -> sqlite3.Connection:
    return get_connection(DB_PATH)


def cmd_team_list(args: argparse.Namespace) -> None:
    """List all teams."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT t.*, m.name as lead_name,
                  (SELECT COUNT(*) FROM team_members tm WHERE tm.team_id = t.id) as member_count
           FROM teams t
           LEFT JOIN members m ON m.id = t.lead_id
           ORDER BY t.name"""
    ).fetchall()

    log_operation("team list")

    if getattr(args, "json", False):
        data = []
        for r in rows:
            d = dict(r)
            data.append(d)
        render_output(data, json_mode=True)
    else:
        if not rows:
            render_output("No teams found. Use `ascend team create` to add one.")
            return
        headers = ["ID", "Name", "Lead", "Members", "Description"]
        table_rows = [
            [str(r["id"]), r["name"], r["lead_name"] or "", str(r["member_count"]), r["description"] or ""]
            for r in rows
        ]
        render_output(format_table(headers, table_rows))
    conn.close()


def cmd_team_create(args: argparse.Namespace) -> None:
    """Create a new team."""
    conn = _get_conn()

    # Check for duplicate
    existing = conn.execute("SELECT id FROM teams WHERE LOWER(name) = LOWER(?)", (args.name,)).fetchone()
    if existing:
        conn.close()
        render_output(f"Error: team '{args.name}' already exists (id={existing['id']})")
        return

    # Resolve lead
    lead_id = None
    if getattr(args, "lead", None):
        lead_row = conn.execute(
            "SELECT id FROM members WHERE LOWER(name) = LOWER(?) OR github = ?",
            (args.lead, args.lead),
        ).fetchone()
        if lead_row:
            lead_id = lead_row["id"]
        else:
            conn.close()
            render_output(f"Error: member '{args.lead}' not found")
            return

    # Resolve parent
    parent_id = None
    if getattr(args, "parent", None):
        parent_row = conn.execute(
            "SELECT id FROM teams WHERE LOWER(name) = LOWER(?)", (args.parent,)
        ).fetchone()
        if parent_row:
            parent_id = parent_row["id"]
        else:
            conn.close()
            render_output(f"Error: parent team '{args.parent}' not found")
            return

    conn.execute(
        """INSERT INTO teams (name, lead_id, parent_id, description)
           VALUES (?, ?, ?, ?)""",
        (args.name, lead_id, parent_id, getattr(args, "description", None)),
    )
    conn.commit()
    team_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    log_operation("team create", args={"name": args.name, "id": team_id})

    if getattr(args, "json", False):
        render_output({"id": team_id, "name": args.name}, json_mode=True)
    else:
        render_output(f"Created team: {args.name} (id={team_id})")


def cmd_team_add(args: argparse.Namespace) -> None:
    """Add a member to a team."""
    conn = _get_conn()

    # Resolve team
    team_row = conn.execute(
        "SELECT id, name FROM teams WHERE LOWER(name) = LOWER(?) OR id = ?",
        (args.team, int(args.team) if args.team.isdigit() else -1),
    ).fetchone()
    if not team_row:
        conn.close()
        render_output(f"Error: team '{args.team}' not found")
        return

    # Resolve member
    member_row = conn.execute(
        "SELECT id, name FROM members WHERE LOWER(name) = LOWER(?) OR github = ? OR id = ?",
        (args.member, args.member, int(args.member) if args.member.isdigit() else -1),
    ).fetchone()
    if not member_row:
        conn.close()
        render_output(f"Error: member '{args.member}' not found")
        return

    role = getattr(args, "role", None) or "member"

    try:
        conn.execute(
            "INSERT INTO team_members (team_id, member_id, role) VALUES (?, ?, ?)",
            (team_row["id"], member_row["id"], role),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        render_output(f"{member_row['name']} is already in {team_row['name']}")
        return

    conn.close()
    log_operation("team add", args={"team": args.team, "member": args.member, "role": role})

    if getattr(args, "json", False):
        render_output({
            "team": team_row["name"],
            "member": member_row["name"],
            "role": role,
        }, json_mode=True)
    else:
        render_output(f"Added {member_row['name']} to {team_row['name']} as {role}")


def cmd_team_show(args: argparse.Namespace) -> None:
    """Show team details and members."""
    conn = _get_conn()

    team_row = conn.execute(
        "SELECT * FROM teams WHERE LOWER(name) = LOWER(?) OR id = ?",
        (args.team, int(args.team) if args.team.isdigit() else -1),
    ).fetchone()
    if not team_row:
        conn.close()
        render_output(f"Error: team '{args.team}' not found")
        return

    # Get lead
    lead_name = None
    if team_row["lead_id"]:
        lead_row = conn.execute("SELECT name FROM members WHERE id = ?", (team_row["lead_id"],)).fetchone()
        if lead_row:
            lead_name = lead_row["name"]

    # Get members
    members = conn.execute(
        """SELECT m.id, m.name, m.github, m.title, m.status, tm.role
           FROM team_members tm
           JOIN members m ON m.id = tm.member_id
           WHERE tm.team_id = ?
           ORDER BY m.name""",
        (team_row["id"],),
    ).fetchall()

    # Get sub-teams
    children = conn.execute(
        "SELECT id, name FROM teams WHERE parent_id = ? ORDER BY name",
        (team_row["id"],),
    ).fetchall()

    conn.close()

    log_operation("team show", args={"team": args.team})

    if getattr(args, "json", False):
        data = dict(team_row)
        data["lead_name"] = lead_name
        data["members"] = [dict(m) for m in members]
        data["children"] = [dict(c) for c in children]
        render_output(data, json_mode=True)
    else:
        lines = [f"## {team_row['name']}\n"]
        if team_row["description"]:
            lines.append(f"{team_row['description']}\n")
        if lead_name:
            lines.append(f"**Lead:** {lead_name}")
        lines.append(f"**Members:** {len(members)}")

        if members:
            lines.append("\n### Members\n")
            headers = ["Name", "GitHub", "Title", "Role", "Status"]
            table_rows = [
                [m["name"], m["github"] or "", m["title"] or "", m["role"], m["status"]]
                for m in members
            ]
            lines.append(format_table(headers, table_rows))

        if children:
            lines.append("\n### Sub-teams\n")
            for c in children:
                lines.append(f"- {c['name']}")

        render_output("\n".join(lines), copy=getattr(args, "copy", False))
