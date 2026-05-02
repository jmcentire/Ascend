# === Ascend CLI Interface (contracts_src_ascend_cli_interface) v1 ===
#  Dependencies: argparse, sys, ascend, ascend.commands.init, ascend.commands.roster, ascend.commands.team, ascend.commands.meeting, ascend.commands.sync, ascend.commands.report, ascend.commands.plan, ascend.commands.coach, ascend.commands.schedule, ascend.tui.app
# Command-line interface for Ascend, an AI-powered engineering management tool. Provides flat subcommand architecture for managing teams, meetings, performance reports, goals, and integrations. Supports space-separated commands (e.g., 'roster list') by rewriting them to hyphenated form (e.g., 'roster-list'). Handles argument parsing and lazy loading of command handlers.

# Module invariants:
#   - All multi-word commands must be accessible via both space-separated and hyphenated forms
#   - Command handlers are always lazy-loaded (imported only when command is invoked)
#   - All subcommands support --json flag for machine-readable output where applicable
#   - Parser program name is always 'ascend'
#   - 3-word command matching takes precedence over 2-word matching in _rewrite_args

SystemExit = primitive  # Built-in exception type for exiting the program with a status code

def _build_parser() -> argparse.ArgumentParser:
    """
    Builds and configures the ArgumentParser for the Ascend CLI with all subcommands and their arguments. Creates approximately 50+ subcommands across categories: init, config, roster, team, meeting, sync, report, plan, coach, and schedule.

    Postconditions:
      - Returns a fully configured ArgumentParser with program name 'ascend'
      - Parser includes --version flag showing ascend version
      - Parser contains subparsers for all CLI commands
      - All subcommands have appropriate arguments defined

    Side effects: none
    Idempotent: no
    """
    ...

def _rewrite_args(
    argv: list[str],
) -> list[str]:
    """
    Rewrites space-separated command arguments to hyphenated form. Supports both 3-word commands (e.g., 'plan goal create' -> 'plan-goal-create') and 2-word commands (e.g., 'roster list' -> 'roster-list'). Tries longest match first (3-word before 2-word).

    Postconditions:
      - Returns rewritten arguments if a known multi-word command is found
      - Returns original arguments unchanged if no match found
      - 3-word commands take precedence over 2-word commands

    Side effects: none
    Idempotent: no
    """
    ...

def main(
    argv: list[str] | None = None,
) -> None:
    """
    CLI entry point. Parses command line arguments, rewrites space-separated commands to hyphenated form, and dispatches to appropriate command handler. Imports command handlers lazily to optimize startup time. Exits with code 1 if no command is provided.

    Postconditions:
      - Command handler is invoked for valid commands
      - Help is printed if no command provided
      - Process exits with code 1 for missing or unknown commands

    Errors:
      - no_command_provided (SystemExit): args.command is falsy
          exit_code: 1
      - unknown_command (SystemExit): args.command does not match any known command
          exit_code: 1

    Side effects: Lazy imports command handler modules based on command, Prints help text to stdout if no command given, Calls sys.exit(1) for error conditions, Invokes command handlers which may have various side effects
    Idempotent: no
    """
    ...

# ── REQUIRED EXPORTS ──────────────────────────────────
# Your implementation module MUST export ALL of these names
# with EXACTLY these spellings. Tests import them by name.
# __all__ = ['_build_parser', '_rewrite_args', 'main', 'SystemExit']
