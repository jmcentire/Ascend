"""Ascend CLI — flat subcommand architecture."""

from __future__ import annotations

import argparse
import sys

from ascend import __version__


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ascend",
        description="AI-powered engineering management CLI",
    )
    parser.add_argument("--version", action="version", version=f"ascend {__version__}")

    sub = parser.add_subparsers(dest="command")

    # -- init --
    p = sub.add_parser("init", help="Initialize ~/.ascend workspace")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- doctor --
    p = sub.add_parser("doctor", help="Diagnose config, integrations, DB health")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- config show --
    p = sub.add_parser("config-show", help="Show configuration")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- config set --
    p = sub.add_parser("config-set", help="Set a configuration value")
    p.add_argument("key", help="Config key")
    p.add_argument("value", help="Config value")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- roster list --
    p = sub.add_parser("roster-list", help="List members")
    p.add_argument("--team", help="Filter by team")
    p.add_argument("--flag", help="Filter by flag")
    p.add_argument("--status", help="Filter by status")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- roster add --
    p = sub.add_parser("roster-add", help="Add a member")
    p.add_argument("name", help="Member name")
    p.add_argument("--email", help="Email address")
    p.add_argument("--github", help="GitHub handle")
    p.add_argument("--slack", help="Slack handle")
    p.add_argument("--phone", help="Phone number")
    p.add_argument("--title", help="Job title")
    p.add_argument("--team", help="Team ID or name")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- roster edit --
    p = sub.add_parser("roster-edit", help="Edit a member")
    p.add_argument("member", help="Member name, github, email, or ID")
    p.add_argument("--name", help="New name")
    p.add_argument("--email", help="New email")
    p.add_argument("--personal-email", dest="personal_email", help="Personal email")
    p.add_argument("--github", help="New GitHub handle")
    p.add_argument("--slack", help="New Slack handle")
    p.add_argument("--phone", help="New phone")
    p.add_argument("--title", help="New title")
    p.add_argument("--team", help="New team ID or name")
    p.add_argument("--status", help="New status")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- roster show --
    p = sub.add_parser("roster-show", help="Show member profile")
    p.add_argument("member", help="Member name, github, email, or ID")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--copy", action="store_true", help="Copy to clipboard")

    # -- roster flag --
    p = sub.add_parser("roster-flag", help="Set a flag on a member")
    p.add_argument("member", help="Member name, github, email, or ID")
    p.add_argument("flag", help="Flag name (oncall, pto, pip, etc.)")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- roster unflag --
    p = sub.add_parser("roster-unflag", help="Remove a flag from a member")
    p.add_argument("member", help="Member name, github, email, or ID")
    p.add_argument("flag", help="Flag name")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- roster search --
    p = sub.add_parser("roster-search", help="Search members")
    p.add_argument("query", help="Search query")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- roster import --
    p = sub.add_parser("roster-import", help="Import members from CSV or team-tracker directory")
    p.add_argument("file", help="Path to CSV file or team-tracker/members/ directory")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- team list --
    p = sub.add_parser("team-list", help="List teams")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- team create --
    p = sub.add_parser("team-create", help="Create a team")
    p.add_argument("name", help="Team name")
    p.add_argument("--lead", help="Team lead (name or github)")
    p.add_argument("--description", help="Team description")
    p.add_argument("--parent", help="Parent team name")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- team add --
    p = sub.add_parser("team-add", help="Add member to team")
    p.add_argument("team", help="Team name or ID")
    p.add_argument("member", help="Member name, github, or ID")
    p.add_argument("--role", help="Role in team (default: member)")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- team show --
    p = sub.add_parser("team-show", help="Show team details")
    p.add_argument("team", help="Team name or ID")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--copy", action="store_true", help="Copy to clipboard")

    # -- meeting ingest --
    p = sub.add_parser("meeting-ingest", help="Ingest transcript file(s)")
    p.add_argument("file", help="Path to transcript file or directory")
    p.add_argument("--member", help="Explicit member (name, github, or ID)")
    p.add_argument("--dry-run", dest="dry_run", action="store_true", help="List files without ingesting")
    p.add_argument("--no-llm", dest="no_llm", action="store_true", help="Store raw text only, no LLM")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- meeting list --
    p = sub.add_parser("meeting-list", help="List meetings")
    p.add_argument("--member", help="Filter by member")
    p.add_argument("--from", dest="from_date", help="Start date (YYYY-MM-DD)")
    p.add_argument("--to", dest="to_date", help="End date (YYYY-MM-DD)")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- meeting show --
    p = sub.add_parser("meeting-show", help="Show meeting details")
    p.add_argument("id", type=int, help="Meeting ID")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--copy", action="store_true", help="Copy to clipboard")

    # -- meeting search --
    p = sub.add_parser("meeting-search", help="Full-text search transcripts")
    p.add_argument("query", help="Search query")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- meeting items --
    p = sub.add_parser("meeting-items", help="List action items")
    p.add_argument("--member", help="Filter by member")
    p.add_argument("--status", choices=["open", "closed", "all"], default="open", help="Item status")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- meeting item-close --
    p = sub.add_parser("meeting-item-close", help="Close an action item")
    p.add_argument("id", type=int, help="Item ID")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- meeting prep --
    p = sub.add_parser("meeting-prep", help="Generate 1:1 prep plan")
    p.add_argument("member", help="Member name, github, or ID")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- sync --
    p = sub.add_parser("sync", help="Run all integrations and take snapshots")
    p.add_argument("--member", help="Filter by member")
    p.add_argument("--hours", type=int, help="Lookback hours")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- sync-github --
    p = sub.add_parser("sync-github", help="Fetch GitHub data")
    p.add_argument("--member", help="Filter by member")
    p.add_argument("--hours", type=int, help="Lookback hours")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- sync-linear --
    p = sub.add_parser("sync-linear", help="Fetch Linear data")
    p.add_argument("--member", help="Filter by member")
    p.add_argument("--hours", type=int, help="Lookback hours")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- sync-slack --
    p = sub.add_parser("sync-slack", help="Fetch Slack data")
    p.add_argument("--hours", type=int, help="Lookback hours")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- sync-snapshot --
    p = sub.add_parser("sync-snapshot", help="Take performance snapshots")
    p.add_argument("--member", help="Filter by member")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- report performance --
    p = sub.add_parser("report-performance", help="Individual performance report")
    p.add_argument("--member", help="Filter by member")
    p.add_argument("--team", help="Filter by team")
    p.add_argument("--days", type=int, default=30, help="Lookback days (default: 30)")
    p.add_argument("--from", dest="from_date", help="Start date (YYYY-MM-DD)")
    p.add_argument("--to", dest="to_date", help="End date (YYYY-MM-DD)")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--copy", action="store_true", help="Copy to clipboard")

    # -- report team --
    p = sub.add_parser("report-team", help="Team health report")
    p.add_argument("--team", help="Filter by team")
    p.add_argument("--days", type=int, default=30, help="Lookback days (default: 30)")
    p.add_argument("--from", dest="from_date", help="Start date (YYYY-MM-DD)")
    p.add_argument("--to", dest="to_date", help="End date (YYYY-MM-DD)")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--copy", action="store_true", help="Copy to clipboard")

    # -- report progress --
    p = sub.add_parser("report-progress", help="Project progress (snapshot trends)")
    p.add_argument("--member", help="Filter by member")
    p.add_argument("--days", type=int, default=30, help="Lookback days (default: 30)")
    p.add_argument("--from", dest="from_date", help="Start date (YYYY-MM-DD)")
    p.add_argument("--to", dest="to_date", help="End date (YYYY-MM-DD)")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--copy", action="store_true", help="Copy to clipboard")

    # -- report git --
    p = sub.add_parser("report-git", help="Git analytics report")
    p.add_argument("--member", help="Filter by member")
    p.add_argument("--days", type=int, default=30, help="Lookback days (default: 30)")
    p.add_argument("--from", dest="from_date", help="Start date (YYYY-MM-DD)")
    p.add_argument("--to", dest="to_date", help="End date (YYYY-MM-DD)")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--copy", action="store_true", help="Copy to clipboard")

    # -- report dashboard --
    p = sub.add_parser("report-dashboard", help="Org-wide dashboard")
    p.add_argument("--days", type=int, default=30, help="Lookback days (default: 30)")
    p.add_argument("--from", dest="from_date", help="Start date (YYYY-MM-DD)")
    p.add_argument("--to", dest="to_date", help="End date (YYYY-MM-DD)")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--copy", action="store_true", help="Copy to clipboard")

    # -- report custom --
    p = sub.add_parser("report-custom", help="Free-form AI report")
    p.add_argument("prompt", help="Report prompt/question")
    p.add_argument("--member", help="Filter by member")
    p.add_argument("--days", type=int, default=30, help="Lookback days (default: 30)")
    p.add_argument("--from", dest="from_date", help="Start date (YYYY-MM-DD)")
    p.add_argument("--to", dest="to_date", help="End date (YYYY-MM-DD)")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--copy", action="store_true", help="Copy to clipboard")

    # -- plan cycle --
    p = sub.add_parser("plan-cycle", help="Show current planning cycle")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- plan goal create --
    p = sub.add_parser("plan-goal-create", help="Create a goal")
    p.add_argument("title", help="Goal title")
    p.add_argument("--member", help="Member name, github, or ID")
    p.add_argument("--team", help="Team name or ID")
    p.add_argument("--cycle", help="Planning cycle (default: current)")
    p.add_argument("--type", choices=["objective", "key_result", "pip_criterion", "career_milestone"],
                   default="objective", help="Goal type")
    p.add_argument("--description", help="Goal description")
    p.add_argument("--target", type=float, help="Target value")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- plan goal list --
    p = sub.add_parser("plan-goal-list", help="List goals")
    p.add_argument("--cycle", help="Planning cycle (default: current)")
    p.add_argument("--status", choices=["active", "completed", "cancelled", "all"], default="active",
                   help="Filter by status")
    p.add_argument("--member", help="Filter by member")
    p.add_argument("--type", help="Filter by type")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- plan goal update --
    p = sub.add_parser("plan-goal-update", help="Update a goal")
    p.add_argument("id", type=int, help="Goal ID")
    p.add_argument("--value", type=float, help="New current value")
    p.add_argument("--status", choices=["active", "completed", "cancelled"], help="New status")
    p.add_argument("--title", help="New title")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- plan pip create --
    p = sub.add_parser("plan-pip-create", help="Create a PIP for a member")
    p.add_argument("member", help="Member name, github, or ID")
    p.add_argument("--criteria", nargs="+", help="PIP criterion titles (or omit for LLM-generated)")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- plan pip show --
    p = sub.add_parser("plan-pip-show", help="Show PIP status")
    p.add_argument("member", help="Member name, github, or ID")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- plan career --
    p = sub.add_parser("plan-career", help="Career development plan")
    p.add_argument("member", help="Member name, github, or ID")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--copy", action="store_true", help="Copy to clipboard")

    # -- coach analyze --
    p = sub.add_parser("coach-analyze", help="Comprehensive member analysis")
    p.add_argument("member", help="Member name, github, or ID")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--copy", action="store_true", help="Copy to clipboard")

    # -- coach risks --
    p = sub.add_parser("coach-risks", help="Risk dashboard")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--copy", action="store_true", help="Copy to clipboard")

    # -- coach star --
    p = sub.add_parser("coach-star", help="Record STAR behavioral assessment")
    p.add_argument("member", help="Member name, github, or ID")
    p.add_argument("--situation", required=True, help="Situation description")
    p.add_argument("--task", required=True, help="Task description")
    p.add_argument("--action", required=True, help="Action taken")
    p.add_argument("--result", required=True, help="Result achieved")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- coach suggest --
    p = sub.add_parser("coach-suggest", help="Coaching suggestions for next 1:1")
    p.add_argument("member", help="Member name, github, or ID")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--copy", action="store_true", help="Copy to clipboard")

    # -- schedule list --
    p = sub.add_parser("schedule-list", help="List all schedules")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- schedule add --
    p = sub.add_parser("schedule-add", help="Add a new schedule")
    p.add_argument("name", help="Schedule name")
    p.add_argument("schedule_command", help="Ascend command to run (e.g., 'sync snapshot')")
    schedule_group = p.add_mutually_exclusive_group(required=True)
    schedule_group.add_argument("--daily", action="store_true", help="Run daily")
    schedule_group.add_argument("--weekdays", action="store_true", help="Run Mon-Fri")
    schedule_group.add_argument("--weekly", metavar="DAY", help="Run weekly on DAY")
    schedule_group.add_argument("--biweekly", metavar="DAY", help="Run 2nd and 4th week on DAY")
    schedule_group.add_argument("--monthly", metavar="DAYS", help="Run on day(s) of month (e.g., 1,15)")
    schedule_group.add_argument("--quarterly", action="store_true", help="Run first day of each quarter")
    p.add_argument("--no-launchd", dest="no_launchd", action="store_true",
                   help="Skip launchd plist generation")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- schedule remove --
    p = sub.add_parser("schedule-remove", help="Remove a schedule")
    p.add_argument("name", help="Schedule name")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- schedule run --
    p = sub.add_parser("schedule-run", help="Run a schedule immediately")
    p.add_argument("name", help="Schedule name")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- schedule enable --
    p = sub.add_parser("schedule-enable", help="Enable a schedule")
    p.add_argument("name", help="Schedule name")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- schedule disable --
    p = sub.add_parser("schedule-disable", help="Disable a schedule")
    p.add_argument("name", help="Schedule name")
    p.add_argument("--json", action="store_true", help="JSON output")

    # -- tui --
    sub.add_parser("tui", help="Launch interactive terminal interface")

    return parser


# Map "space" style commands (ascend roster list) to flat hyphenated commands
_SPACE_TO_FLAT = {}


def _rewrite_args(argv: list[str]) -> list[str]:
    """Rewrite 'ascend roster list' to 'ascend roster-list'.

    Supports 3-word commands (plan goal create) and 2-word commands.
    Tries longest match first.
    """
    # Try 3-word match first
    if len(argv) >= 3:
        candidate3 = f"{argv[0]}-{argv[1]}-{argv[2]}"
        if candidate3 in (
            "plan-goal-create", "plan-goal-list", "plan-goal-update",
            "plan-pip-create", "plan-pip-show",
        ):
            return [candidate3] + argv[3:]
    # Try 2-word match
    if len(argv) >= 2:
        candidate = f"{argv[0]}-{argv[1]}"
        if candidate in (
            "roster-list", "roster-add", "roster-edit", "roster-show",
            "roster-flag", "roster-unflag", "roster-search", "roster-import",
            "team-list", "team-create", "team-add", "team-show",
            "config-show", "config-set",
            "meeting-ingest", "meeting-list", "meeting-show", "meeting-search",
            "meeting-items", "meeting-item-close", "meeting-prep",
            "sync-github", "sync-linear", "sync-slack", "sync-snapshot",
            "report-performance", "report-team", "report-progress",
            "report-git", "report-dashboard", "report-custom",
            "plan-cycle", "plan-career",
            "coach-analyze", "coach-risks", "coach-star", "coach-suggest",
            "schedule-list", "schedule-add", "schedule-remove",
            "schedule-run", "schedule-enable", "schedule-disable",
        ):
            return [candidate] + argv[2:]
    return argv


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = _build_parser()

    raw_args = argv if argv is not None else sys.argv[1:]
    rewritten = _rewrite_args(raw_args)
    args = parser.parse_args(rewritten)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Import handlers lazily to keep startup fast
    if args.command == "init":
        from ascend.commands.init import cmd_init
        cmd_init(args)

    elif args.command == "doctor":
        from ascend.commands.init import cmd_doctor
        cmd_doctor(args)

    elif args.command == "config-show":
        from ascend.commands.init import cmd_config_show
        cmd_config_show(args)

    elif args.command == "config-set":
        from ascend.commands.init import cmd_config_set
        cmd_config_set(args)

    elif args.command == "roster-list":
        from ascend.commands.roster import cmd_roster_list
        cmd_roster_list(args)

    elif args.command == "roster-add":
        from ascend.commands.roster import cmd_roster_add
        cmd_roster_add(args)

    elif args.command == "roster-edit":
        from ascend.commands.roster import cmd_roster_edit
        cmd_roster_edit(args)

    elif args.command == "roster-show":
        from ascend.commands.roster import cmd_roster_show
        cmd_roster_show(args)

    elif args.command == "roster-flag":
        from ascend.commands.roster import cmd_roster_flag
        cmd_roster_flag(args)

    elif args.command == "roster-unflag":
        from ascend.commands.roster import cmd_roster_unflag
        cmd_roster_unflag(args)

    elif args.command == "roster-search":
        from ascend.commands.roster import cmd_roster_search
        cmd_roster_search(args)

    elif args.command == "roster-import":
        from ascend.commands.roster import cmd_roster_import
        cmd_roster_import(args)

    elif args.command == "team-list":
        from ascend.commands.team import cmd_team_list
        cmd_team_list(args)

    elif args.command == "team-create":
        from ascend.commands.team import cmd_team_create
        cmd_team_create(args)

    elif args.command == "team-add":
        from ascend.commands.team import cmd_team_add
        cmd_team_add(args)

    elif args.command == "team-show":
        from ascend.commands.team import cmd_team_show
        cmd_team_show(args)

    elif args.command == "meeting-ingest":
        from ascend.commands.meeting import cmd_meeting_ingest
        cmd_meeting_ingest(args)

    elif args.command == "meeting-list":
        from ascend.commands.meeting import cmd_meeting_list
        cmd_meeting_list(args)

    elif args.command == "meeting-show":
        from ascend.commands.meeting import cmd_meeting_show
        cmd_meeting_show(args)

    elif args.command == "meeting-search":
        from ascend.commands.meeting import cmd_meeting_search
        cmd_meeting_search(args)

    elif args.command == "meeting-items":
        from ascend.commands.meeting import cmd_meeting_items
        cmd_meeting_items(args)

    elif args.command == "meeting-item-close":
        from ascend.commands.meeting import cmd_meeting_item_close
        cmd_meeting_item_close(args)

    elif args.command == "meeting-prep":
        from ascend.commands.meeting import cmd_meeting_prep
        cmd_meeting_prep(args)

    elif args.command == "sync":
        from ascend.commands.sync import cmd_sync
        cmd_sync(args)

    elif args.command == "sync-github":
        from ascend.commands.sync import cmd_sync_github
        cmd_sync_github(args)

    elif args.command == "sync-linear":
        from ascend.commands.sync import cmd_sync_linear
        cmd_sync_linear(args)

    elif args.command == "sync-slack":
        from ascend.commands.sync import cmd_sync_slack
        cmd_sync_slack(args)

    elif args.command == "sync-snapshot":
        from ascend.commands.sync import cmd_sync_snapshot
        cmd_sync_snapshot(args)

    elif args.command == "report-performance":
        from ascend.commands.report import cmd_report_performance
        cmd_report_performance(args)

    elif args.command == "report-team":
        from ascend.commands.report import cmd_report_team
        cmd_report_team(args)

    elif args.command == "report-progress":
        from ascend.commands.report import cmd_report_progress
        cmd_report_progress(args)

    elif args.command == "report-git":
        from ascend.commands.report import cmd_report_git
        cmd_report_git(args)

    elif args.command == "report-dashboard":
        from ascend.commands.report import cmd_report_dashboard
        cmd_report_dashboard(args)

    elif args.command == "report-custom":
        from ascend.commands.report import cmd_report_custom
        cmd_report_custom(args)

    elif args.command == "plan-cycle":
        from ascend.commands.plan import cmd_plan_cycle
        cmd_plan_cycle(args)

    elif args.command == "plan-goal-create":
        from ascend.commands.plan import cmd_plan_goal_create
        cmd_plan_goal_create(args)

    elif args.command == "plan-goal-list":
        from ascend.commands.plan import cmd_plan_goal_list
        cmd_plan_goal_list(args)

    elif args.command == "plan-goal-update":
        from ascend.commands.plan import cmd_plan_goal_update
        cmd_plan_goal_update(args)

    elif args.command == "plan-pip-create":
        from ascend.commands.plan import cmd_plan_pip_create
        cmd_plan_pip_create(args)

    elif args.command == "plan-pip-show":
        from ascend.commands.plan import cmd_plan_pip_show
        cmd_plan_pip_show(args)

    elif args.command == "plan-career":
        from ascend.commands.plan import cmd_plan_career
        cmd_plan_career(args)

    elif args.command == "coach-analyze":
        from ascend.commands.coach import cmd_coach_analyze
        cmd_coach_analyze(args)

    elif args.command == "coach-risks":
        from ascend.commands.coach import cmd_coach_risks
        cmd_coach_risks(args)

    elif args.command == "coach-star":
        from ascend.commands.coach import cmd_coach_star
        cmd_coach_star(args)

    elif args.command == "coach-suggest":
        from ascend.commands.coach import cmd_coach_suggest
        cmd_coach_suggest(args)

    elif args.command == "schedule-list":
        from ascend.commands.schedule import cmd_schedule_list
        cmd_schedule_list(args)

    elif args.command == "schedule-add":
        from ascend.commands.schedule import cmd_schedule_add
        cmd_schedule_add(args)

    elif args.command == "schedule-remove":
        from ascend.commands.schedule import cmd_schedule_remove
        cmd_schedule_remove(args)

    elif args.command == "schedule-run":
        from ascend.commands.schedule import cmd_schedule_run
        cmd_schedule_run(args)

    elif args.command == "schedule-enable":
        from ascend.commands.schedule import cmd_schedule_enable
        cmd_schedule_enable(args)

    elif args.command == "schedule-disable":
        from ascend.commands.schedule import cmd_schedule_disable
        cmd_schedule_disable(args)

    elif args.command == "tui":
        from ascend.tui.app import AscendApp
        AscendApp().run()

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
