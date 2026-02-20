"""Scheduler — cron parsing, next-run computation, launchd plist generation."""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Day name → cron weekday (0=Sunday in cron, but Python weekday 0=Monday)
_DAY_MAP = {
    "sunday": 0, "sun": 0,
    "monday": 1, "mon": 1,
    "tuesday": 2, "tue": 2,
    "wednesday": 3, "wed": 3,
    "thursday": 4, "thu": 4,
    "friday": 5, "fri": 5,
    "saturday": 6, "sat": 6,
}

_CRON_WEEKDAY_TO_PYTHON = {0: 6, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}

_PLIST_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{ascend_path}</string>
        <string>schedule</string>
        <string>run</string>
        <string>{schedule_name}</string>
    </array>
    <key>StartCalendarInterval</key>
{calendar_intervals}
    <key>StandardOutPath</key>
    <string>{log_path}</string>
    <key>StandardErrorPath</key>
    <string>{log_path}</string>
</dict>
</plist>
"""


def schedule_to_cron(
    *,
    daily: bool = False,
    weekdays: bool = False,
    weekly: Optional[str] = None,
    biweekly: Optional[str] = None,
    monthly: Optional[str] = None,
    quarterly: bool = False,
    hour: int = 9,
    minute: int = 0,
) -> str:
    """Convert human-friendly schedule spec to a cron expression.

    Returns a standard 5-field cron: minute hour day-of-month month day-of-week
    """
    if daily:
        return f"{minute} {hour} * * *"
    if weekdays:
        return f"{minute} {hour} * * 1-5"
    if weekly:
        day = _DAY_MAP.get(weekly.lower())
        if day is None:
            raise ValueError(f"Unknown day: {weekly}")
        return f"{minute} {hour} * * {day}"
    if biweekly:
        day = _DAY_MAP.get(biweekly.lower())
        if day is None:
            raise ValueError(f"Unknown day: {biweekly}")
        # Biweekly: 2nd and 4th occurrence → days 8-14 and 22-28
        return f"{minute} {hour} 8-14,22-28 * {day}"
    if monthly:
        # monthly is a comma-separated string of day numbers
        return f"{minute} {hour} {monthly} * *"
    if quarterly:
        # First day of each quarter
        return f"{minute} {hour} 1 1,4,7,10 *"
    raise ValueError("No schedule frequency specified")


def parse_cron(expr: str) -> dict:
    """Parse a 5-field cron expression into components.

    Returns dict with keys: minute, hour, dom, month, dow
    Each value is a string (may contain *, ranges, lists).
    """
    parts = expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Expected 5 cron fields, got {len(parts)}: {expr}")
    return {
        "minute": parts[0],
        "hour": parts[1],
        "dom": parts[2],
        "month": parts[3],
        "dow": parts[4],
    }


def _expand_field(field: str, min_val: int, max_val: int) -> set[int]:
    """Expand a cron field into a set of integer values."""
    if field == "*":
        return set(range(min_val, max_val + 1))
    values: set[int] = set()
    for part in field.split(","):
        if "-" in part:
            start, end = part.split("-", 1)
            values.update(range(int(start), int(end) + 1))
        else:
            values.add(int(part))
    return values


def compute_next_run(cron_expr: str, after: Optional[datetime] = None) -> str:
    """Compute next run time from a cron expression.

    Returns ISO format datetime string.
    """
    if after is None:
        after = datetime.now()

    fields = parse_cron(cron_expr)
    minutes = _expand_field(fields["minute"], 0, 59)
    hours = _expand_field(fields["hour"], 0, 23)
    doms = _expand_field(fields["dom"], 1, 31)
    months = _expand_field(fields["month"], 1, 12)
    dows = _expand_field(fields["dow"], 0, 6)

    dom_any = fields["dom"] == "*"
    dow_any = fields["dow"] == "*"

    # Start searching from the next minute
    candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)

    # Search up to 366 days ahead
    max_search = after + timedelta(days=366)

    while candidate < max_search:
        if candidate.month not in months:
            # Jump to first day of next valid month
            candidate = candidate.replace(day=1, hour=0, minute=0) + timedelta(days=32)
            candidate = candidate.replace(day=1, hour=0, minute=0)
            continue

        # Cron semantics: if both dom and dow are restricted (not *),
        # match on EITHER. If only one is restricted, match on that one.
        day_match = True
        if dom_any and dow_any:
            day_match = True
        elif dom_any:
            # Convert Python weekday (Mon=0) to cron weekday (Sun=0)
            cron_dow = (candidate.weekday() + 1) % 7
            day_match = cron_dow in dows
        elif dow_any:
            day_match = candidate.day in doms
        else:
            # Both restricted: OR semantics
            cron_dow = (candidate.weekday() + 1) % 7
            day_match = candidate.day in doms or cron_dow in dows

        if not day_match:
            candidate = candidate.replace(hour=0, minute=0) + timedelta(days=1)
            continue

        if candidate.hour not in hours:
            candidate = candidate.replace(minute=0) + timedelta(hours=1)
            continue

        if candidate.minute not in minutes:
            candidate += timedelta(minutes=1)
            continue

        return candidate.strftime("%Y-%m-%d %H:%M")

    return ""


def describe_cron(cron_expr: str) -> str:
    """Return a human-readable description of a cron expression."""
    fields = parse_cron(cron_expr)

    time_str = f"{int(fields['hour']):02d}:{int(fields['minute']):02d}" if fields["hour"] != "*" else ""

    if fields["dom"] == "*" and fields["month"] == "*" and fields["dow"] == "*":
        return f"daily at {time_str}" if time_str else "every minute"

    if fields["dom"] == "*" and fields["month"] == "*" and fields["dow"] == "1-5":
        return f"weekdays at {time_str}" if time_str else "weekdays"

    if fields["dom"] == "*" and fields["month"] == "*" and fields["dow"] != "*":
        day_names = {0: "Sun", 1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat"}
        dows = _expand_field(fields["dow"], 0, 6)
        days = ", ".join(day_names.get(d, str(d)) for d in sorted(dows))
        return f"every {days} at {time_str}" if time_str else f"every {days}"

    if fields["dow"] == "*" and fields["month"] == "*":
        return f"monthly on day(s) {fields['dom']} at {time_str}" if time_str else f"monthly on {fields['dom']}"

    if fields["month"] != "*" and fields["dom"] != "*":
        return f"on day {fields['dom']} of months {fields['month']} at {time_str}"

    return cron_expr


def _find_ascend_path() -> str:
    """Find the ascend executable path."""
    path = shutil.which("ascend")
    if path:
        return path
    # Fallback: try common locations
    for candidate in ["/usr/local/bin/ascend", str(Path.home() / ".local/bin/ascend")]:
        if Path(candidate).exists():
            return candidate
    return "ascend"


def _cron_to_calendar_intervals(cron_expr: str) -> str:
    """Convert cron expression to launchd CalendarInterval XML."""
    fields = parse_cron(cron_expr)
    intervals = []

    minutes = _expand_field(fields["minute"], 0, 59)
    hours = _expand_field(fields["hour"], 0, 23)

    # For simple cases, generate one or a few intervals
    minute_val = min(minutes) if len(minutes) <= 2 else 0
    hour_val = min(hours) if len(hours) <= 2 else 9

    if fields["dom"] == "*" and fields["month"] == "*" and fields["dow"] == "*":
        # Daily
        intervals.append({"Hour": hour_val, "Minute": minute_val})
    elif fields["dow"] == "1-5":
        # Weekdays
        for dow in range(1, 6):
            intervals.append({"Weekday": dow, "Hour": hour_val, "Minute": minute_val})
    elif fields["dow"] != "*" and fields["dom"] == "*":
        # Specific weekdays
        for dow in _expand_field(fields["dow"], 0, 6):
            intervals.append({"Weekday": dow, "Hour": hour_val, "Minute": minute_val})
    elif fields["dom"] != "*" and fields["month"] != "*":
        # Specific months and days
        for month in _expand_field(fields["month"], 1, 12):
            for day in _expand_field(fields["dom"], 1, 31):
                intervals.append({"Month": month, "Day": day, "Hour": hour_val, "Minute": minute_val})
    elif fields["dom"] != "*":
        # Specific days of month
        for day in _expand_field(fields["dom"], 1, 31):
            intervals.append({"Day": day, "Hour": hour_val, "Minute": minute_val})
    else:
        intervals.append({"Hour": hour_val, "Minute": minute_val})

    # Build XML
    if len(intervals) == 1:
        xml = "    <dict>\n"
        for k, v in intervals[0].items():
            xml += f"        <key>{k}</key>\n        <integer>{v}</integer>\n"
        xml += "    </dict>"
    else:
        xml = "    <array>\n"
        for interval in intervals:
            xml += "        <dict>\n"
            for k, v in interval.items():
                xml += f"            <key>{k}</key>\n            <integer>{v}</integer>\n"
            xml += "        </dict>\n"
        xml += "    </array>"
    return xml


def generate_plist(schedule_name: str, schedules_dir: Path) -> str:
    """Generate a launchd plist file for a schedule.

    Returns the plist content as a string.
    """
    label = f"com.ascend.schedule.{schedule_name}"
    ascend_path = _find_ascend_path()
    log_path = str(schedules_dir / f"{schedule_name}.log")

    # We need the cron expression to generate calendar intervals,
    # but this function generates a template. The caller fills in the intervals.
    return label, ascend_path, log_path


def write_plist(
    schedule_name: str,
    cron_expr: str,
    schedules_dir: Path,
) -> Optional[Path]:
    """Write a launchd plist file and return its path."""
    label = f"com.ascend.schedule.{schedule_name}"
    ascend_path = _find_ascend_path()
    log_path = str(schedules_dir / f"{schedule_name}.log")
    calendar_xml = _cron_to_calendar_intervals(cron_expr)

    content = _PLIST_TEMPLATE.format(
        label=label,
        ascend_path=ascend_path,
        schedule_name=schedule_name,
        calendar_intervals=calendar_xml,
        log_path=log_path,
    )

    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist_path = plist_dir / f"{label}.plist"
    plist_path.write_text(content)
    return plist_path


def load_plist(schedule_name: str) -> bool:
    """Load a launchd plist. Returns True on success."""
    label = f"com.ascend.schedule.{schedule_name}"
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    if not plist_path.exists():
        return False
    try:
        subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True, timeout=10)
        return True
    except Exception:
        return False


def unload_plist(schedule_name: str) -> bool:
    """Unload a launchd plist. Returns True on success."""
    label = f"com.ascend.schedule.{schedule_name}"
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    if not plist_path.exists():
        return False
    try:
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True, timeout=10)
        return True
    except Exception:
        return False


def remove_plist(schedule_name: str) -> bool:
    """Unload and remove a launchd plist. Returns True on success."""
    unload_plist(schedule_name)
    label = f"com.ascend.schedule.{schedule_name}"
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    if plist_path.exists():
        plist_path.unlink()
        return True
    return False
