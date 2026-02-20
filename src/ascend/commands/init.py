"""ascend init / doctor / config commands."""

from __future__ import annotations

import argparse
import os

from ascend.audit import log_operation
from ascend.config import (
    ASCEND_HOME,
    CONFIG_PATH,
    DB_PATH,
    HISTORY_DIR,
    SCHEDULES_DIR,
    TRANSCRIPTS_DIR,
    AscendConfig,
    get_config_value,
    load_config,
    save_config,
    set_config_value,
)
from ascend.db import check_db, init_db
from ascend.output import format_table, print_report, print_status, render_output


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize the ~/.ascend workspace."""
    # Create directories
    for d in [ASCEND_HOME, HISTORY_DIR, TRANSCRIPTS_DIR, SCHEDULES_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # Initialize config if missing
    if not CONFIG_PATH.exists():
        cfg = AscendConfig()
        save_config(cfg)
        print_status(f"Created config at {CONFIG_PATH}")
    else:
        print_status(f"Config already exists at {CONFIG_PATH}")

    # Initialize database
    conn = init_db(DB_PATH)
    conn.close()
    print_status(f"Database initialized at {DB_PATH}")

    log_operation("init")

    if getattr(args, "json", False):
        render_output({"status": "initialized", "home": str(ASCEND_HOME)}, json_mode=True)
    else:
        print_report(f"## Ascend initialized\n\nWorkspace: `{ASCEND_HOME}`")


def cmd_doctor(args: argparse.Namespace) -> None:
    """Diagnose config, integrations, and DB health."""
    checks = []

    # Config
    config_ok = CONFIG_PATH.exists()
    checks.append(("Config file", "ok" if config_ok else "missing", str(CONFIG_PATH)))

    # Database
    db_info = check_db(DB_PATH)
    checks.append(("Database", "ok" if db_info["ok"] else db_info.get("error", "error"), str(DB_PATH)))
    if db_info["ok"]:
        checks.append(("Schema version", str(db_info["version"]), ""))
        for table, count in db_info.get("tables", {}).items():
            checks.append((f"  {table}", str(count), "rows"))

    # API key
    cfg = load_config() if config_ok else AscendConfig()
    api_key = os.environ.get(cfg.anthropic_api_key_env, "")
    checks.append(("Anthropic API key", "set" if api_key else "not set", cfg.anthropic_api_key_env))

    # History dir
    history_ok = HISTORY_DIR.exists()
    checks.append(("History directory", "ok" if history_ok else "missing", str(HISTORY_DIR)))

    # Repos dir
    repos_ok = os.path.isdir(cfg.repos_dir)
    checks.append(("Repos directory", "ok" if repos_ok else "missing", cfg.repos_dir))

    log_operation("doctor")

    if getattr(args, "json", False):
        render_output({"checks": [{"name": c[0], "status": c[1], "detail": c[2]} for c in checks]}, json_mode=True)
    else:
        lines = ["## Ascend Doctor\n"]
        all_ok = True
        for name, status, detail in checks:
            if status in ("ok", "set") or status.isdigit():
                icon = "+"
            elif status == "missing" or status == "not set":
                icon = "-"
                all_ok = False
            else:
                icon = "!"
                all_ok = False
            suffix = f"  ({detail})" if detail else ""
            lines.append(f"  [{icon}] {name}: {status}{suffix}")

        lines.append("")
        if all_ok:
            lines.append("All checks passed.")
        else:
            lines.append("Some checks failed. Run `ascend init` to fix.")
        print_report("\n".join(lines))


def cmd_config_show(args: argparse.Namespace) -> None:
    """Show current configuration."""
    cfg = load_config()
    data = cfg.model_dump()
    log_operation("config show")

    if getattr(args, "json", False):
        render_output(data, json_mode=True)
    else:
        lines = ["## Ascend Configuration\n"]
        for key, value in data.items():
            lines.append(f"  {key}: {value}")
        print_report("\n".join(lines))


def cmd_config_set(args: argparse.Namespace) -> None:
    """Set a configuration value."""
    try:
        cfg = set_config_value(args.key, args.value)
        log_operation("config set", args={"key": args.key, "value": args.value})
        if getattr(args, "json", False):
            render_output({"key": args.key, "value": getattr(cfg, args.key)}, json_mode=True)
        else:
            print_report(f"Set `{args.key}` = `{args.value}`")
    except KeyError as e:
        if getattr(args, "json", False):
            render_output({"error": str(e)}, json_mode=True)
        else:
            print_report(f"Error: {e}")
