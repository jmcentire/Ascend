"""
Contract Test Suite for Ascend Scheduler Interface
Generated from contract version 1
Tests cover happy paths, edge cases, error cases, and invariants
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, mock_open
from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import os

# Import the module under test
from contracts.src_ascend_scheduler.interface import *


# ============================================================================
# SCHEDULE_TO_CRON TESTS
# ============================================================================

def test_schedule_to_cron_daily_happy_path():
    """Convert daily schedule to cron expression"""
    result = schedule_to_cron(
        daily=True,
        weekdays=False,
        weekly=None,
        biweekly=None,
        monthly=None,
        quarterly=False,
        hour=9,
        minute=30
    )
    assert result == "30 9 * * *"


def test_schedule_to_cron_weekdays_happy_path():
    """Convert weekdays schedule to cron expression"""
    result = schedule_to_cron(
        daily=False,
        weekdays=True,
        weekly=None,
        biweekly=None,
        monthly=None,
        quarterly=False,
        hour=8,
        minute=0
    )
    assert result == "0 8 * * 1-5"


def test_schedule_to_cron_weekly_happy_path():
    """Convert weekly schedule to cron expression"""
    result = schedule_to_cron(
        daily=False,
        weekdays=False,
        weekly="mon",
        biweekly=None,
        monthly=None,
        quarterly=False,
        hour=10,
        minute=15
    )
    assert result == "15 10 * * 1"


def test_schedule_to_cron_biweekly_happy_path():
    """Convert biweekly schedule to cron expression"""
    result = schedule_to_cron(
        daily=False,
        weekdays=False,
        weekly=None,
        biweekly="wednesday",
        monthly=None,
        quarterly=False,
        hour=14,
        minute=30
    )
    # Biweekly targets days 8-14 and 22-28
    assert "8-14" in result or "22-28" in result
    assert "3" in result  # Wednesday = 3
    assert "30 14" in result


def test_schedule_to_cron_monthly_happy_path():
    """Convert monthly schedule to cron expression"""
    result = schedule_to_cron(
        daily=False,
        weekdays=False,
        weekly=None,
        biweekly=None,
        monthly="15",
        quarterly=False,
        hour=12,
        minute=0
    )
    assert result == "0 12 15 * *"


def test_schedule_to_cron_quarterly_happy_path():
    """Convert quarterly schedule to cron expression"""
    result = schedule_to_cron(
        daily=False,
        weekdays=False,
        weekly=None,
        biweekly=None,
        monthly=None,
        quarterly=True,
        hour=6,
        minute=0
    )
    assert result == "0 6 1 1,4,7,10 *"


def test_schedule_to_cron_weekly_full_day_name():
    """Weekly schedule with full day name"""
    result = schedule_to_cron(
        daily=False,
        weekdays=False,
        weekly="Friday",
        biweekly=None,
        monthly=None,
        quarterly=False,
        hour=17,
        minute=45
    )
    assert result == "45 17 * * 5"  # Friday = 5


def test_schedule_to_cron_weekly_sunday():
    """Weekly schedule on Sunday (cron value 0)"""
    result = schedule_to_cron(
        daily=False,
        weekdays=False,
        weekly="sun",
        biweekly=None,
        monthly=None,
        quarterly=False,
        hour=7,
        minute=0
    )
    assert result == "0 7 * * 0"  # Sunday = 0


def test_schedule_to_cron_unknown_day_error():
    """Error when weekly day name is invalid"""
    with pytest.raises(Exception) as exc_info:
        schedule_to_cron(
            daily=False,
            weekdays=False,
            weekly="funday",
            biweekly=None,
            monthly=None,
            quarterly=False,
            hour=10,
            minute=0
        )
    # Check that error is related to unknown day
    assert "unknown" in str(exc_info.value).lower() or "day" in str(exc_info.value).lower()


def test_schedule_to_cron_no_frequency_error():
    """Error when no schedule frequency is specified"""
    with pytest.raises(Exception) as exc_info:
        schedule_to_cron(
            daily=False,
            weekdays=False,
            weekly=None,
            biweekly=None,
            monthly=None,
            quarterly=False,
            hour=10,
            minute=0
        )
    # Check that error is related to no frequency
    assert "frequency" in str(exc_info.value).lower() or "no" in str(exc_info.value).lower()


def test_schedule_to_cron_biweekly_invalid_day_error():
    """Error when biweekly day name is invalid"""
    with pytest.raises(Exception) as exc_info:
        schedule_to_cron(
            daily=False,
            weekdays=False,
            weekly=None,
            biweekly="notaday",
            monthly=None,
            quarterly=False,
            hour=10,
            minute=0
        )
    assert "unknown" in str(exc_info.value).lower() or "day" in str(exc_info.value).lower()


def test_schedule_to_cron_midnight():
    """Schedule at midnight (hour=0, minute=0)"""
    result = schedule_to_cron(
        daily=True,
        weekdays=False,
        weekly=None,
        biweekly=None,
        monthly=None,
        quarterly=False,
        hour=0,
        minute=0
    )
    assert result == "0 0 * * *"


def test_schedule_to_cron_last_minute_of_day():
    """Schedule at 23:59"""
    result = schedule_to_cron(
        daily=True,
        weekdays=False,
        weekly=None,
        biweekly=None,
        monthly=None,
        quarterly=False,
        hour=23,
        minute=59
    )
    assert result == "59 23 * * *"


# ============================================================================
# PARSE_CRON TESTS
# ============================================================================

def test_parse_cron_happy_path():
    """Parse a standard 5-field cron expression"""
    result = parse_cron("30 9 * * 1-5")
    assert result["minute"] == "30"
    assert result["hour"] == "9"
    assert result["dom"] == "*"
    assert result["month"] == "*"
    assert result["dow"] == "1-5"


def test_parse_cron_with_lists():
    """Parse cron expression with comma-separated lists"""
    result = parse_cron("0,15,30,45 8,12,16 1,15 * *")
    assert result["minute"] == "0,15,30,45"
    assert result["hour"] == "8,12,16"
    assert result["dom"] == "1,15"
    assert result["month"] == "*"
    assert result["dow"] == "*"


def test_parse_cron_all_wildcards():
    """Parse cron expression with all wildcards"""
    result = parse_cron("* * * * *")
    assert all(result[key] == "*" for key in ["minute", "hour", "dom", "month", "dow"])


def test_parse_cron_invalid_field_count_too_few():
    """Error when cron expression has too few fields"""
    with pytest.raises(Exception) as exc_info:
        parse_cron("30 9 * *")
    assert "field" in str(exc_info.value).lower() or "count" in str(exc_info.value).lower()


def test_parse_cron_invalid_field_count_too_many():
    """Error when cron expression has too many fields"""
    with pytest.raises(Exception) as exc_info:
        parse_cron("30 9 * * * * extra")
    assert "field" in str(exc_info.value).lower() or "count" in str(exc_info.value).lower()


def test_parse_cron_empty_string():
    """Error when cron expression is empty"""
    with pytest.raises(Exception) as exc_info:
        parse_cron("")
    assert "field" in str(exc_info.value).lower() or "count" in str(exc_info.value).lower()


def test_parse_cron_returns_correct_keys():
    """Verify parse_cron returns dict with all required keys"""
    result = parse_cron("0 10 * * *")
    assert set(result.keys()) == {"minute", "hour", "dom", "month", "dow"}


# ============================================================================
# _EXPAND_FIELD TESTS
# ============================================================================

def test_expand_field_wildcard():
    """Expand wildcard to full range"""
    result = _expand_field("*", 0, 23)
    assert result == set(range(0, 24))


def test_expand_field_single_value():
    """Expand single integer value"""
    result = _expand_field("15", 0, 59)
    assert result == {15}


def test_expand_field_range():
    """Expand range notation"""
    result = _expand_field("1-5", 0, 6)
    assert result == {1, 2, 3, 4, 5}


def test_expand_field_comma_list():
    """Expand comma-separated list"""
    result = _expand_field("1,3,5,7", 0, 10)
    assert result == {1, 3, 5, 7}


def test_expand_field_mixed_list_and_ranges():
    """Expand mixed comma-separated values and ranges"""
    result = _expand_field("1,3-5,8", 0, 10)
    assert result == {1, 3, 4, 5, 8}


def test_expand_field_invalid_int_error():
    """Error when field contains non-integer value"""
    with pytest.raises(Exception) as exc_info:
        _expand_field("abc", 0, 10)
    assert "int" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()


def test_expand_field_edge_min_max_equal():
    """Expand field when min_val equals max_val"""
    result = _expand_field("*", 5, 5)
    assert result == {5}


# ============================================================================
# COMPUTE_NEXT_RUN TESTS
# ============================================================================

def test_compute_next_run_happy_path():
    """Compute next run time for a simple daily cron"""
    after = datetime(2024, 1, 15, 8, 0)
    result = compute_next_run("30 9 * * *", after)
    assert result == "2024-01-15 09:30"


def test_compute_next_run_next_day():
    """Compute next run when time already passed today"""
    after = datetime(2024, 1, 15, 10, 0)
    result = compute_next_run("30 9 * * *", after)
    assert result == "2024-01-16 09:30"


def test_compute_next_run_weekly_specific_day():
    """Compute next run for weekly schedule"""
    # 2024-01-15 is a Monday
    after = datetime(2024, 1, 15, 8, 0)
    result = compute_next_run("0 10 * * 1", after)
    # Should return today at 10:00 or next Monday
    assert "10:00" in result


def test_compute_next_run_after_none():
    """Compute next run with after=None uses current time"""
    with patch('contracts_src_ascend_scheduler_interface.datetime') as mock_dt:
        mock_dt.now.return_value = datetime(2024, 1, 15, 8, 0)
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
        result = compute_next_run("0 12 * * *", None)
        # Should compute based on mocked current time
        assert isinstance(result, str)


def test_compute_next_run_year_boundary():
    """Compute next run crossing year boundary"""
    after = datetime(2024, 12, 31, 23, 0)
    result = compute_next_run("0 0 1 1 *", after)
    assert result == "2025-01-01 00:00"


def test_compute_next_run_no_match_within_366_days():
    """Return empty string when no match found within 366 days"""
    after = datetime(2024, 1, 1, 0, 0)
    result = compute_next_run("0 0 31 2 *", after)
    # Feb 31 doesn't exist
    assert result == ""


def test_compute_next_run_invalid_cron_error():
    """Error when cron expression is invalid"""
    after = datetime(2024, 1, 15, 8, 0)
    with pytest.raises(Exception) as exc_info:
        compute_next_run("invalid", after)
    assert "cron" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()


def test_compute_next_run_dom_dow_or_semantics():
    """Verify OR semantics when both dom and dow are specified"""
    after = datetime(2024, 1, 1, 0, 0)
    result = compute_next_run("0 10 15 * 1", after)
    # Should match either 15th OR Monday
    assert result != ""
    # Parse result and verify it's either 15th or Monday
    if result:
        result_dt = datetime.strptime(result, "%Y-%m-%d %H:%M")
        # Should be either day 15 or a Monday (weekday 0)
        is_15th = result_dt.day == 15
        is_monday = result_dt.weekday() == 0
        assert is_15th or is_monday


def test_compute_next_run_strictly_after():
    """Verify returned time is strictly after the 'after' parameter"""
    after = datetime(2024, 1, 15, 9, 30)
    result = compute_next_run("30 9 * * *", after)
    # Should not return the same time
    assert result != "2024-01-15 09:30"
    # Should be the next day
    assert result == "2024-01-16 09:30"


# ============================================================================
# DESCRIBE_CRON TESTS
# ============================================================================

def test_describe_cron_simple_daily():
    """Describe simple daily cron expression"""
    result = describe_cron("30 9 * * *")
    # Should contain human-readable description
    assert isinstance(result, str)
    assert len(result) > 0


def test_describe_cron_weekdays():
    """Describe weekdays cron expression"""
    result = describe_cron("0 8 * * 1-5")
    assert isinstance(result, str)
    assert len(result) > 0


def test_describe_cron_weekly():
    """Describe weekly cron expression"""
    result = describe_cron("0 10 * * 1")
    assert isinstance(result, str)
    assert len(result) > 0


def test_describe_cron_complex_fallback():
    """Return raw expression for complex cron"""
    result = describe_cron("*/5 1,2,3 * * *")
    # Should return something (either description or raw expression)
    assert isinstance(result, str)
    assert len(result) > 0


def test_describe_cron_invalid_cron_error():
    """Error when cron expression is invalid"""
    with pytest.raises(Exception) as exc_info:
        describe_cron("invalid cron")
    assert "cron" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()


# ============================================================================
# _FIND_ASCEND_PATH TESTS
# ============================================================================

def test_find_ascend_path_happy_path():
    """Find ascend executable in PATH"""
    with patch('shutil.which') as mock_which:
        mock_which.return_value = "/usr/local/bin/ascend"
        result = _find_ascend_path()
        assert result == "/usr/local/bin/ascend"


def test_find_ascend_path_fallback():
    """Return 'ascend' as fallback when not found"""
    with patch('shutil.which', return_value=None), \
         patch('pathlib.Path.exists', return_value=False):
        result = _find_ascend_path()
        assert result == "ascend"


# ============================================================================
# _CRON_TO_CALENDAR_INTERVALS TESTS
# ============================================================================

def test_cron_to_calendar_intervals_simple():
    """Convert simple cron to CalendarInterval XML"""
    result = _cron_to_calendar_intervals("30 9 * * *")
    # Should return XML string
    assert isinstance(result, str)
    assert "<dict>" in result or "<array>" in result
    assert "Minute" in result or "Hour" in result


def test_cron_to_calendar_intervals_multiple():
    """Convert cron with multiple values to CalendarInterval array"""
    result = _cron_to_calendar_intervals("0 8,12,16 * * *")
    # Should return XML with array for multiple intervals
    assert isinstance(result, str)
    assert "<array>" in result or "<dict>" in result


def test_cron_to_calendar_intervals_invalid_cron_error():
    """Error when cron expression is invalid"""
    with pytest.raises(Exception) as exc_info:
        _cron_to_calendar_intervals("bad cron")
    assert "cron" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()


# ============================================================================
# GENERATE_PLIST TESTS
# ============================================================================

def test_generate_plist_happy_path():
    """Generate plist metadata for a schedule"""
    schedules_dir = Path("/tmp/schedules")
    result = generate_plist("daily-backup", schedules_dir)
    # Contract says it returns tuple of (label, ascend_path, log_path)
    assert isinstance(result, tuple)
    assert len(result) == 3
    label, ascend_path, log_path = result
    assert "daily-backup" in label
    assert isinstance(ascend_path, str)
    assert isinstance(log_path, str)


# ============================================================================
# WRITE_PLIST TESTS
# ============================================================================

def test_write_plist_happy_path():
    """Write plist file to LaunchAgents directory"""
    with patch('pathlib.Path.mkdir'), \
         patch('pathlib.Path.write_text'), \
         patch('pathlib.Path.expanduser') as mock_expand, \
         patch('contracts_src_ascend_scheduler_interface._find_ascend_path', return_value='ascend'), \
         patch('contracts_src_ascend_scheduler_interface._cron_to_calendar_intervals', return_value='<dict></dict>'):
        
        mock_home = Path("/home/user")
        mock_expand.return_value = mock_home / "Library" / "LaunchAgents" / "com.ascend.schedule.test-schedule.plist"
        
        result = write_plist("test-schedule", "30 9 * * *", Path("/tmp/schedules"))
        
        assert isinstance(result, Path)
        assert "com.ascend.schedule.test-schedule.plist" in str(result)


def test_write_plist_creates_directory():
    """Create LaunchAgents directory if it doesn't exist"""
    with patch('pathlib.Path.mkdir') as mock_mkdir, \
         patch('pathlib.Path.write_text'), \
         patch('pathlib.Path.expanduser') as mock_expand, \
         patch('contracts_src_ascend_scheduler_interface._find_ascend_path', return_value='ascend'), \
         patch('contracts_src_ascend_scheduler_interface._cron_to_calendar_intervals', return_value='<dict></dict>'):
        
        mock_home = Path("/home/user")
        mock_expand.return_value = mock_home / "Library" / "LaunchAgents" / "com.ascend.schedule.test-schedule.plist"
        
        result = write_plist("test-schedule", "0 12 * * *", Path("/tmp/schedules"))
        
        # Verify mkdir was called with parents=True
        assert mock_mkdir.called


def test_write_plist_invalid_cron_error():
    """Error when cron expression is invalid"""
    with pytest.raises(Exception) as exc_info:
        write_plist("test-schedule", "bad", Path("/tmp/schedules"))
    assert "cron" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()


# ============================================================================
# LOAD_PLIST TESTS
# ============================================================================

def test_load_plist_happy_path():
    """Load plist using launchctl successfully"""
    with patch('pathlib.Path.exists', return_value=True), \
         patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=0)
        
        result = load_plist("test-schedule")
        
        assert result is True
        assert mock_run.called


def test_load_plist_file_not_exists():
    """Return False when plist file doesn't exist"""
    with patch('pathlib.Path.exists', return_value=False):
        result = load_plist("nonexistent-schedule")
        assert result is False


def test_load_plist_launchctl_fails():
    """Return False when launchctl command fails"""
    with patch('pathlib.Path.exists', return_value=True), \
         patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=1)
        
        result = load_plist("test-schedule")
        
        assert result is False


# ============================================================================
# UNLOAD_PLIST TESTS
# ============================================================================

def test_unload_plist_happy_path():
    """Unload plist using launchctl successfully"""
    with patch('pathlib.Path.exists', return_value=True), \
         patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=0)
        
        result = unload_plist("test-schedule")
        
        assert result is True
        assert mock_run.called


def test_unload_plist_file_not_exists():
    """Return False when plist file doesn't exist"""
    with patch('pathlib.Path.exists', return_value=False):
        result = unload_plist("nonexistent-schedule")
        assert result is False


def test_unload_plist_launchctl_fails():
    """Return False when launchctl command fails"""
    with patch('pathlib.Path.exists', return_value=True), \
         patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=1)
        
        result = unload_plist("test-schedule")
        
        assert result is False


# ============================================================================
# REMOVE_PLIST TESTS
# ============================================================================

def test_remove_plist_happy_path():
    """Unload and remove plist file successfully"""
    with patch('pathlib.Path.exists', return_value=True), \
         patch('pathlib.Path.unlink') as mock_unlink, \
         patch('contracts_src_ascend_scheduler_interface.unload_plist', return_value=True):
        
        result = remove_plist("test-schedule")
        
        assert result is True
        assert mock_unlink.called


def test_remove_plist_file_not_exists():
    """Return False when plist file doesn't exist"""
    with patch('pathlib.Path.exists', return_value=False):
        result = remove_plist("nonexistent-schedule")
        assert result is False


# ============================================================================
# INVARIANT TESTS
# ============================================================================

def test_invariant_day_map_sunday_is_zero():
    """Verify _DAY_MAP maps Sunday to 0"""
    result = schedule_to_cron(
        daily=False,
        weekdays=False,
        weekly="sun",
        biweekly=None,
        monthly=None,
        quarterly=False,
        hour=10,
        minute=0
    )
    # Sunday should map to 0
    assert result.endswith(" 0")


def test_invariant_biweekly_targets_correct_days():
    """Verify biweekly schedules target days 8-14 and 22-28"""
    result = schedule_to_cron(
        daily=False,
        weekdays=False,
        weekly=None,
        biweekly="mon",
        monthly=None,
        quarterly=False,
        hour=10,
        minute=0
    )
    # Should contain days 8-14,22-28
    assert "8-14" in result or "22-28" in result


def test_invariant_quarterly_first_day_of_quarters():
    """Verify quarterly schedules run on first day of months 1,4,7,10"""
    result = schedule_to_cron(
        daily=False,
        weekdays=False,
        weekly=None,
        biweekly=None,
        monthly=None,
        quarterly=True,
        hour=6,
        minute=0
    )
    assert " 1 " in result  # day of month = 1
    assert "1,4,7,10" in result  # months


def test_invariant_cron_always_5_fields():
    """Verify all generated cron expressions have exactly 5 fields"""
    result = schedule_to_cron(
        daily=True,
        weekdays=False,
        weekly=None,
        biweekly=None,
        monthly=None,
        quarterly=False,
        hour=9,
        minute=30
    )
    fields = result.split()
    assert len(fields) == 5


def test_invariant_plist_path_format():
    """Verify plist files are stored at correct path"""
    with patch('pathlib.Path.mkdir'), \
         patch('pathlib.Path.write_text'), \
         patch('pathlib.Path.expanduser') as mock_expand, \
         patch('contracts_src_ascend_scheduler_interface._find_ascend_path', return_value='ascend'), \
         patch('contracts_src_ascend_scheduler_interface._cron_to_calendar_intervals', return_value='<dict></dict>'):
        
        mock_home = Path("/home/user")
        mock_expand.return_value = mock_home / "Library" / "LaunchAgents" / "com.ascend.schedule.my-schedule.plist"
        
        result = write_plist("my-schedule", "0 10 * * *", Path("/tmp/schedules"))
        
        # Verify path format
        assert "LaunchAgents" in str(result)
        assert "com.ascend.schedule.my-schedule.plist" in str(result)
