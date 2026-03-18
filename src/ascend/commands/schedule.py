"""Schedule commands — list, add, remove, run, enable, disable."""

from __future__ import annotations

import argparse
import shlex
import sqlite3
from datetime import datetime
from typing import Optional

from ascend.audit import log_operation
from ascend.config import DB_PATH, SCHEDULES_DIR, load_config
from ascend.db import get_connection
from ascend.output import format_table, render_output
from ascend.scheduler import (
    compute_next_run,
    describe_cron,
    remove_plist,
    schedule_to_cron,
    write_plist,
)


def _get_conn() -> sqlite3.Connection:
    return get_connection(DB_PATH)


# ---- Schedule: List ----

def cmd_schedule_list(args: argparse.Namespace) -> None:
    """List all schedules."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)

    rows = conn.execute("SELECT * FROM schedules ORDER BY name").fetchall()
    schedules = [dict(r) for r in rows]

    conn.close()
    log_operation("schedule list")

    if json_mode:
        render_output(schedules, json_mode=True)
    else:
        if not schedules:
            render_output("No schedules configured.")
            return
        headers = ["Name", "Command", "Schedule", "Enabled", "Last Run", "Next Run"]
        rows_data = []
        for s in schedules:
            desc = describe_cron(s["cron_expr"]) if s["cron_expr"] else s["cron_expr"]
            rows_data.append([
                s["name"],
                s["command"],
                desc,
                "yes" if s["enabled"] else "no",
                s["last_run"] or "-",
                s["next_run"] or "-",
            ])
        render_output(format_table(headers, rows_data))


# ---- Schedule: Add ----

def cmd_schedule_add(args: argparse.Namespace) -> None:
    """Add a new schedule."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)

    name = args.name
    command = args.schedule_command

    # Check for duplicate
    existing = conn.execute("SELECT 1 FROM schedules WHERE name = ?", (name,)).fetchone()
    if existing:
        conn.close()
        render_output({"error": f"schedule '{name}' already exists"}, json_mode=True)
        return

    # Build cron expression from flags
    try:
        cron_expr = schedule_to_cron(
            daily=getattr(args, "daily", False),
            weekdays=getattr(args, "weekdays", False),
            weekly=getattr(args, "weekly", None),
            biweekly=getattr(args, "biweekly", None),
            monthly=getattr(args, "monthly", None),
            quarterly=getattr(args, "quarterly", False),
        )
    except ValueError as e:
        conn.close()
        render_output({"error": str(e)}, json_mode=True)
        return

    next_run = compute_next_run(cron_expr)

    conn.execute(
        """INSERT INTO schedules (name, command, cron_expr, next_run, enabled)
           VALUES (?, ?, ?, ?, 1)""",
        (name, command, cron_expr, next_run),
    )
    conn.commit()

    result = {
        "name": name,
        "command": command,
        "cron_expr": cron_expr,
        "description": describe_cron(cron_expr),
        "next_run": next_run,
        "enabled": True,
    }

    # Generate launchd plist (best effort)
    plist_path = None
    if not getattr(args, "no_launchd", False):
        try:
            SCHEDULES_DIR.mkdir(parents=True, exist_ok=True)
            plist_path = write_plist(name, cron_expr, SCHEDULES_DIR)
            result["plist"] = str(plist_path)
        except Exception as e:
            result["plist_error"] = str(e)

    conn.close()
    log_operation("schedule add", args={"name": name, "command": command, "cron": cron_expr})

    if json_mode:
        render_output(result, json_mode=True)
    else:
        parts = [f"Schedule '{name}' created."]
        parts.append(f"  Command: {command}")
        parts.append(f"  Schedule: {result['description']}")
        parts.append(f"  Cron: {cron_expr}")
        parts.append(f"  Next run: {next_run}")
        if plist_path:
            parts.append(f"  Plist: {plist_path}")
        render_output("\n".join(parts))


# ---- Schedule: Remove ----

def cmd_schedule_remove(args: argparse.Namespace) -> None:
    """Remove a schedule."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    name = args.name

    row = conn.execute("SELECT * FROM schedules WHERE name = ?", (name,)).fetchone()
    if not row:
        conn.close()
        render_output({"error": f"schedule '{name}' not found"}, json_mode=True)
        return

    conn.execute("DELETE FROM schedules WHERE name = ?", (name,))
    conn.commit()
    conn.close()

    # Remove launchd plist (best effort)
    remove_plist(name)

    log_operation("schedule remove", args={"name": name})

    if json_mode:
        render_output({"removed": name}, json_mode=True)
    else:
        render_output(f"Schedule '{name}' removed.")


# ---- Schedule: Run ----

def cmd_schedule_run(args: argparse.Namespace) -> None:
    """Run a schedule immediately."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    name = args.name

    row = conn.execute("SELECT * FROM schedules WHERE name = ?", (name,)).fetchone()
    if not row:
        conn.close()
        render_output({"error": f"schedule '{name}' not found"}, json_mode=True)
        return

    command = row["command"]
    cron_expr = row["cron_expr"]

    # Execute the command by calling main() with the command args
    import io
    import sys

    from ascend.cli import main as ascend_main

    argv = shlex.split(command)
    # Strip leading 'ascend' from stored command — main() expects args only, not program name
    if argv and argv[0] == "ascend":
        argv = argv[1:]
    error = None
    try:
        if json_mode:
            # Suppress inner command output in JSON mode to avoid mixed output
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                ascend_main(argv)
            finally:
                sys.stdout = old_stdout
        else:
            ascend_main(argv)
    except SystemExit:
        pass
    except Exception as e:
        error = str(e)

    # Update last_run and next_run
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    next_run = compute_next_run(cron_expr)
    conn.execute(
        "UPDATE schedules SET last_run = ?, next_run = ? WHERE name = ?",
        (now_str, next_run, name),
    )
    conn.commit()
    conn.close()

    log_operation("schedule run", args={"name": name, "command": command})

    if json_mode:
        result = {
            "name": name,
            "command": command,
            "ran_at": now_str,
            "next_run": next_run,
            "error": error,
        }
        render_output(result, json_mode=True)


# ---- Schedule: Enable ----

def cmd_schedule_enable(args: argparse.Namespace) -> None:
    """Enable a schedule."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    name = args.name

    row = conn.execute("SELECT * FROM schedules WHERE name = ?", (name,)).fetchone()
    if not row:
        conn.close()
        render_output({"error": f"schedule '{name}' not found"}, json_mode=True)
        return

    next_run = compute_next_run(row["cron_expr"])
    conn.execute(
        "UPDATE schedules SET enabled = 1, next_run = ? WHERE name = ?",
        (next_run, name),
    )
    conn.commit()
    conn.close()

    log_operation("schedule enable", args={"name": name})

    if json_mode:
        render_output({"name": name, "enabled": True, "next_run": next_run}, json_mode=True)
    else:
        render_output(f"Schedule '{name}' enabled. Next run: {next_run}")


# ---- Schedule: Disable ----

def cmd_schedule_disable(args: argparse.Namespace) -> None:
    """Disable a schedule."""
    conn = _get_conn()
    json_mode = getattr(args, "json", False)
    name = args.name

    row = conn.execute("SELECT * FROM schedules WHERE name = ?", (name,)).fetchone()
    if not row:
        conn.close()
        render_output({"error": f"schedule '{name}' not found"}, json_mode=True)
        return

    conn.execute("UPDATE schedules SET enabled = 0, next_run = NULL WHERE name = ?", (name,))
    conn.commit()
    conn.close()

    log_operation("schedule disable", args={"name": name})

    if json_mode:
        render_output({"name": name, "enabled": False}, json_mode=True)
    else:
        render_output(f"Schedule '{name}' disabled.")
