# === Ascend Scheduler (src_ascend_scheduler) v1 ===
#  Dependencies: shutil, subprocess, datetime, pathlib, typing
# Cron expression parsing, next-run computation, and macOS launchd plist generation for scheduled job management. Converts human-friendly schedule specifications to cron expressions, computes next run times, and manages launchd plists for periodic task execution.

# Module invariants:
#   - Cron weekday 0 = Sunday (differs from Python's datetime.weekday() where 0 = Monday)
#   - Cron expressions are always 5 fields: minute hour day-of-month month day-of-week
#   - When both day-of-month and day-of-week are restricted (not *), cron uses OR semantics (match either)
#   - compute_next_run searches up to 366 days ahead before giving up
#   - launchd plist files are stored in ~/Library/LaunchAgents/
#   - launchd plist label format: com.ascend.schedule.{schedule_name}
#   - Schedule log files use format: {schedules_dir}/{schedule_name}.log
#   - _PLIST_TEMPLATE defines XML structure for macOS launchd configuration
#   - Biweekly schedules target 2nd and 4th occurrences (days 8-14 and 22-28)
#   - Quarterly schedules run on 1st day of Jan, Apr, Jul, Oct

class _DAY_MAP:
    """Mapping from day names (full and abbreviated) to cron weekday numbers (0=Sunday)"""
    sunday: int                              # required, Sunday = 0
    sun: int                                 # required, Sunday = 0
    monday: int                              # required, Monday = 1
    mon: int                                 # required, Monday = 1
    tuesday: int                             # required, Tuesday = 2
    tue: int                                 # required, Tuesday = 2
    wednesday: int                           # required, Wednesday = 3
    wed: int                                 # required, Wednesday = 3
    thursday: int                            # required, Thursday = 4
    thu: int                                 # required, Thursday = 4
    friday: int                              # required, Friday = 5
    fri: int                                 # required, Friday = 5
    saturday: int                            # required, Saturday = 6
    sat: int                                 # required, Saturday = 6

class _CRON_WEEKDAY_TO_PYTHON:
    """Mapping from cron weekday numbers (0=Sunday) to Python weekday numbers (0=Monday, 6=Sunday)"""
    0: int                                   # required, Cron Sunday (0) -> Python Sunday (6)
    1: int                                   # required, Cron Monday (1) -> Python Monday (0)
    2: int                                   # required, Cron Tuesday (2) -> Python Tuesday (1)
    3: int                                   # required, Cron Wednesday (3) -> Python Wednesday (2)
    4: int                                   # required, Cron Thursday (4) -> Python Thursday (3)
    5: int                                   # required, Cron Friday (5) -> Python Friday (4)
    6: int                                   # required, Cron Saturday (6) -> Python Saturday (5)

class CronFields:
    """Dictionary representing parsed cron expression fields"""
    minute: str                              # required, Minute field (0-59, *, ranges, lists)
    hour: str                                # required, Hour field (0-23, *, ranges, lists)
    dom: str                                 # required, Day of month field (1-31, *, ranges, lists)
    month: str                               # required, Month field (1-12, *, ranges, lists)
    dow: str                                 # required, Day of week field (0-6, *, ranges, lists, 0=Sunday)

def schedule_to_cron(
    daily: bool,
    weekdays: bool,
    weekly: Optional[str],
    biweekly: Optional[str],
    monthly: Optional[str],
    quarterly: bool,
    hour: int,
    minute: int,
) -> str:
    """
    Convert human-friendly schedule specification to a standard 5-field cron expression (minute hour day-of-month month day-of-week).

    Preconditions:
      - At least one schedule frequency parameter (daily, weekdays, weekly, biweekly, monthly, quarterly) must be truthy
      - If weekly or biweekly is provided, the day name must exist in _DAY_MAP

    Postconditions:
      - Returns a valid 5-field cron expression string
      - Cron format is: 'minute hour day-of-month month day-of-week'

    Errors:
      - UnknownDayError (ValueError): weekly or biweekly day name not in _DAY_MAP (case-insensitive)
          message: Unknown day: {day_name}
      - NoScheduleError (ValueError): No schedule frequency parameter is specified
          message: No schedule frequency specified

    Side effects: none
    Idempotent: no
    """
    ...

def parse_cron(
    expr: str,
) -> dict:
    """
    Parse a 5-field cron expression into a dictionary with named components.

    Preconditions:
      - expr must contain exactly 5 whitespace-separated fields

    Postconditions:
      - Returns dict with keys: minute, hour, dom, month, dow
      - Each value is the original string field (may contain *, ranges, lists)

    Errors:
      - InvalidCronFieldCount (ValueError): expr does not contain exactly 5 fields after splitting by whitespace
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
    Expand a cron field (*, range, list) into a set of integer values within the given bounds.

    Preconditions:
      - field contains only *, digits, commas, and hyphens
      - Range syntax uses single hyphen between two integers

    Postconditions:
      - Returns set of all matching integer values in [min_val, max_val]
      - '*' expands to all values in range
      - Comma-separated values are unioned
      - Range 'a-b' expands to all integers from a to b inclusive

    Errors:
      - InvalidFieldFormat (ValueError): field contains non-numeric characters outside of valid syntax

    Side effects: none
    Idempotent: no
    """
    ...

def compute_next_run(
    cron_expr: str,
    after: Optional[datetime],
) -> str:
    """
    Compute the next scheduled run time from a cron expression, searching up to 366 days ahead. Uses cron OR-semantics when both day-of-month and day-of-week are restricted.

    Preconditions:
      - cron_expr is a valid 5-field cron expression

    Postconditions:
      - Returns ISO format datetime string 'YYYY-MM-DD HH:MM' if a match is found within 366 days
      - Returns empty string '' if no match found within 366 days
      - Returned time is strictly after the 'after' parameter
      - Seconds and microseconds are zeroed out

    Errors:
      - InvalidCronExpression (ValueError): cron_expr cannot be parsed by parse_cron

    Side effects: none
    Idempotent: no
    """
    ...

def describe_cron(
    cron_expr: str,
) -> str:
    """
    Convert a cron expression to a human-readable English description.

    Preconditions:
      - cron_expr is a valid 5-field cron expression

    Postconditions:
      - Returns human-readable schedule description
      - Falls back to returning the original cron_expr if no pattern matches

    Errors:
      - InvalidCronExpression (ValueError): cron_expr cannot be parsed by parse_cron

    Side effects: none
    Idempotent: no
    """
    ...

def _find_ascend_path() -> str:
    """
    Locate the ascend executable by searching PATH and common installation locations.

    Postconditions:
      - Returns path to ascend executable if found via shutil.which or common locations
      - Returns 'ascend' as fallback if not found (relies on PATH at runtime)

    Side effects: none
    Idempotent: no
    """
    ...

def _cron_to_calendar_intervals(
    cron_expr: str,
) -> str:
    """
    Convert a cron expression to launchd StartCalendarInterval XML format.

    Preconditions:
      - cron_expr is a valid 5-field cron expression

    Postconditions:
      - Returns XML string representing launchd CalendarInterval dict or array
      - Single interval: returns <dict>...</dict>
      - Multiple intervals: returns <array><dict>...</dict>...</array>
      - Simplifies complex schedules by selecting min values for minute/hour if <= 2 values, else defaults to 0 or 9

    Errors:
      - InvalidCronExpression (ValueError): cron_expr cannot be parsed

    Side effects: none
    Idempotent: no
    """
    ...

def generate_plist(
    schedule_name: str,
    schedules_dir: Path,
) -> str:
    """
    Generate metadata for a launchd plist (label, ascend path, log path). Returns a 3-tuple instead of plist content.

    Postconditions:
      - Returns tuple of (label, ascend_path, log_path)
      - label format: 'com.ascend.schedule.{schedule_name}'
      - log_path format: '{schedules_dir}/{schedule_name}.log'

    Side effects: none
    Idempotent: no
    """
    ...

def write_plist(
    schedule_name: str,
    cron_expr: str,
    schedules_dir: Path,
) -> Optional[Path]:
    """
    Generate and write a launchd plist file to ~/Library/LaunchAgents/ for the given schedule.

    Preconditions:
      - cron_expr is a valid 5-field cron expression

    Postconditions:
      - Creates ~/Library/LaunchAgents directory if it doesn't exist
      - Writes plist file to ~/Library/LaunchAgents/com.ascend.schedule.{schedule_name}.plist
      - Returns Path to written plist file
      - Plist contains zsh invocation: '/bin/zsh -l -c {ascend_path} schedule-run {schedule_name}'

    Errors:
      - InvalidCronExpression (ValueError): cron_expr cannot be converted to calendar intervals

    Side effects: none
    Idempotent: no
    """
    ...

def load_plist(
    schedule_name: str,
) -> bool:
    """
    Load a launchd plist using launchctl. Returns True on success, False on failure.

    Postconditions:
      - Returns False if plist file doesn't exist
      - Returns True if launchctl load succeeds
      - Returns False if launchctl load fails or times out

    Side effects: none
    Idempotent: no
    """
    ...

def unload_plist(
    schedule_name: str,
) -> bool:
    """
    Unload a launchd plist using launchctl. Returns True on success, False on failure.

    Postconditions:
      - Returns False if plist file doesn't exist
      - Returns True if launchctl unload succeeds
      - Returns False if launchctl unload fails or times out

    Side effects: none
    Idempotent: no
    """
    ...

def remove_plist(
    schedule_name: str,
) -> bool:
    """
    Unload and delete a launchd plist file. Returns True if file was deleted, False otherwise.

    Postconditions:
      - Calls unload_plist first to unload the job
      - Returns True if plist file existed and was deleted
      - Returns False if plist file doesn't exist

    Side effects: none
    Idempotent: no
    """
    ...

# ── REQUIRED EXPORTS ──────────────────────────────────
# Your implementation module MUST export ALL of these names
# with EXACTLY these spellings. Tests import them by name.
# __all__ = ['_DAY_MAP', '_CRON_WEEKDAY_TO_PYTHON', 'CronFields', 'schedule_to_cron', 'parse_cron', '_expand_field', 'compute_next_run', 'describe_cron', '_find_ascend_path', '_cron_to_calendar_intervals', 'generate_plist', 'write_plist', 'load_plist', 'unload_plist', 'remove_plist']
