# === Ascend Scheduler Interface (contracts_src_ascend_scheduler_interface) v1 ===
#  Dependencies: shutil, subprocess, datetime, pathlib, typing
# Cron parsing, next-run computation, and launchd plist generation for scheduled task management. Converts human-friendly schedule specifications to cron expressions, computes next run times, and generates/manages macOS launchd plist files for scheduling.

# Module invariants:
#   - _DAY_MAP maps day names (full and abbreviated) to cron weekday values (0=Sunday)
#   - _CRON_WEEKDAY_TO_PYTHON maps cron weekday (0=Sunday) to Python weekday (0=Monday)
#   - Cron expressions are always 5 fields: minute hour dom month dow
#   - Biweekly schedules target days 8-14 and 22-28 to approximate 2nd and 4th occurrences
#   - Quarterly schedules run on first day of months 1,4,7,10
#   - Plist files are stored at ~/Library/LaunchAgents/com.ascend.schedule.{name}.plist
#   - When both dom and dow are restricted (not *), cron uses OR semantics (match either)
#   - compute_next_run searches up to 366 days ahead for next match
#   - launchctl commands timeout after 10 seconds

class CronFields:
    """Dictionary containing parsed cron expression fields"""
    minute: str                              # required, Minute field (0-59, *, or range)
    hour: str                                # required, Hour field (0-23, *, or range)
    dom: str                                 # required, Day of month field (1-31, *, or range)
    month: str                               # required, Month field (1-12, *, or range)
    dow: str                                 # required, Day of week field (0-6, *, or range, 0=Sunday in cron)

def schedule_to_cron(
    daily: bool = False,
    weekdays: bool = False,
    weekly: Optional[str] = None,
    biweekly: Optional[str] = None,
    monthly: Optional[str] = None,
    quarterly: bool = False,
    hour: int = 9,
    minute: int = 0,
) -> str:
    """
    Convert human-friendly schedule spec to a 5-field cron expression (minute hour day-of-month month day-of-week)

    Preconditions:
      - At least one schedule frequency flag must be True or set
      - If weekly or biweekly is set, day name must be valid (sun/mon/tue/wed/thu/fri/sat or full name)
      - Only one schedule frequency should be specified

    Postconditions:
      - Returns valid 5-field cron expression string

    Errors:
      - unknown_day (ValueError): weekly or biweekly day name not in _DAY_MAP
          message: Unknown day: {day}
      - no_frequency (ValueError): No schedule frequency parameter is truthy
          message: No schedule frequency specified

    Side effects: none
    Idempotent: no
    """
    ...

def parse_cron(
    expr: str,
) -> dict:
    """
    Parse a 5-field cron expression into components dictionary with keys: minute, hour, dom, month, dow

    Preconditions:
      - expr must contain exactly 5 whitespace-separated fields

    Postconditions:
      - Returns dict with keys: minute, hour, dom, month, dow
      - Each value is a string (may contain *, ranges, lists)

    Errors:
      - invalid_field_count (ValueError): expr does not contain exactly 5 fields
          message: Expected 5 cron fields, got {count}: {expr}

    Side effects: none
    Idempotent: no
    """
    ...

def _expand_field(
    field: str,
    min_val: int,
    max_val: int,
) -> set[int]:
    """
    Expand a cron field into a set of integer values. Handles wildcards (*), ranges (1-5), and comma-separated lists.

    Preconditions:
      - field contains valid cron syntax (*, ranges, or integers)
      - min_val <= max_val

    Postconditions:
      - Returns set of integers within [min_val, max_val]
      - * expands to full range
      - Ranges like '1-5' expand to {1,2,3,4,5}
      - Comma-separated values are combined

    Errors:
      - invalid_int (ValueError): field contains non-integer values when not * or range

    Side effects: none
    Idempotent: no
    """
    ...

def compute_next_run(
    cron_expr: str,
    after: Optional[datetime] = None,
) -> str:
    """
    Compute next run time from a cron expression using proper cron semantics (OR logic for dom/dow when both specified). Returns ISO format datetime string or empty string if no match found within 366 days.

    Preconditions:
      - cron_expr is a valid 5-field cron expression

    Postconditions:
      - Returns datetime string in format '%Y-%m-%d %H:%M' if match found within 366 days
      - Returns empty string if no match found within 366 days
      - Returned time is strictly after the 'after' parameter

    Errors:
      - invalid_cron (ValueError): parse_cron fails on cron_expr

    Side effects: Calls datetime.now() if after is None
    Idempotent: no
    """
    ...

def describe_cron(
    cron_expr: str,
) -> str:
    """
    Return a human-readable description of a cron expression. Falls back to returning the raw expression for complex cases.

    Preconditions:
      - cron_expr is a valid 5-field cron expression

    Postconditions:
      - Returns human-readable description or raw cron_expr for complex cases

    Errors:
      - invalid_cron (ValueError): parse_cron fails on cron_expr
      - invalid_int_conversion (ValueError): hour or minute field cannot be converted to int for simple cases

    Side effects: none
    Idempotent: no
    """
    ...

def _find_ascend_path() -> str:
    """
    Find the ascend executable path by checking PATH, then common install locations. Returns 'ascend' as fallback.

    Postconditions:
      - Returns path to ascend executable if found
      - Returns 'ascend' as fallback if not found

    Side effects: Checks system PATH via shutil.which, Checks filesystem for /usr/local/bin/ascend and ~/.local/bin/ascend
    Idempotent: no
    """
    ...

def _cron_to_calendar_intervals(
    cron_expr: str,
) -> str:
    """
    Convert cron expression to launchd CalendarInterval XML format. Generates simplified intervals for common patterns.

    Preconditions:
      - cron_expr is a valid 5-field cron expression

    Postconditions:
      - Returns XML string representing CalendarInterval dict or array
      - Single interval returns <dict>, multiple intervals return <array>

    Errors:
      - invalid_cron (ValueError): parse_cron fails

    Side effects: none
    Idempotent: no
    """
    ...

def generate_plist(
    schedule_name: str,
    schedules_dir: Path,
) -> str:
    """
    Generate launchd plist metadata (label, ascend_path, log_path) for a schedule. Note: actual implementation returns tuple, not plist content string.

    Postconditions:
      - Returns tuple of (label, ascend_path, log_path)

    Side effects: Calls _find_ascend_path() which checks filesystem
    Idempotent: no
    """
    ...

def write_plist(
    schedule_name: str,
    cron_expr: str,
    schedules_dir: Path,
) -> Optional[Path]:
    """
    Write a launchd plist file to ~/Library/LaunchAgents/ and return its path. Creates directory if needed.

    Preconditions:
      - cron_expr is a valid 5-field cron expression

    Postconditions:
      - Plist file written to ~/Library/LaunchAgents/com.ascend.schedule.{schedule_name}.plist
      - Directory ~/Library/LaunchAgents created if not exists
      - Returns Path to written plist file

    Errors:
      - invalid_cron (ValueError): cron_expr is invalid
      - write_error (OSError): File write fails

    Side effects: Creates directory ~/Library/LaunchAgents if not exists, Writes plist file to filesystem
    Idempotent: no
    """
    ...

def load_plist(
    schedule_name: str,
) -> bool:
    """
    Load a launchd plist using launchctl. Returns True on success, False otherwise.

    Preconditions:
      - Plist file exists at ~/Library/LaunchAgents/com.ascend.schedule.{schedule_name}.plist

    Postconditions:
      - Returns True if plist exists and launchctl load succeeds
      - Returns False if plist doesn't exist or load fails

    Side effects: Executes launchctl load command, Checks filesystem for plist existence
    Idempotent: no
    """
    ...

def unload_plist(
    schedule_name: str,
) -> bool:
    """
    Unload a launchd plist using launchctl. Returns True on success, False otherwise.

    Preconditions:
      - Plist file exists at ~/Library/LaunchAgents/com.ascend.schedule.{schedule_name}.plist

    Postconditions:
      - Returns True if plist exists and launchctl unload succeeds
      - Returns False if plist doesn't exist or unload fails

    Side effects: Executes launchctl unload command, Checks filesystem for plist existence
    Idempotent: no
    """
    ...

def remove_plist(
    schedule_name: str,
) -> bool:
    """
    Unload and remove a launchd plist file. Returns True if file was removed, False otherwise.

    Postconditions:
      - Plist file is unloaded (if loaded)
      - Plist file is deleted from filesystem (if exists)
      - Returns True if file existed and was removed
      - Returns False if file didn't exist

    Side effects: Calls unload_plist which runs launchctl, Deletes plist file from filesystem
    Idempotent: no
    """
    ...

# ── REQUIRED EXPORTS ──────────────────────────────────
# Your implementation module MUST export ALL of these names
# with EXACTLY these spellings. Tests import them by name.
# __all__ = ['CronFields', 'schedule_to_cron', 'parse_cron', '_expand_field', 'compute_next_run', 'describe_cron', '_find_ascend_path', '_cron_to_calendar_intervals', 'generate_plist', 'write_plist', 'load_plist', 'unload_plist', 'remove_plist']
