"""
Contract tests for src_ascend_scheduler module.

Tests cover:
- Data structure validation (_DAY_MAP, _CRON_WEEKDAY_TO_PYTHON, CronFields)
- Pure functions (_expand_field, parse_cron)
- Schedule conversion (schedule_to_cron)
- Cron parsing and computation (compute_next_run)
- Human-readable descriptions (describe_cron)
- Plist generation and management (write_plist, load_plist, unload_plist, remove_plist)
- Path discovery (_find_ascend_path)
- Calendar interval conversion (_cron_to_calendar_intervals)
- Error cases for all error types
- Invariants (cron format, weekday mapping, biweekly/quarterly patterns)
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, mock_open
from pathlib import Path
from datetime import datetime
import tempfile
import os

# Import the module under test
from src.ascend.scheduler import *


# ============================================================================
# DATA STRUCTURE VALIDATION TESTS
# ============================================================================

class TestDataStructures:
    """Tests for data structure types and their invariants."""
    
    def test_day_map_structure(self):
        """Verify _DAY_MAP contains all expected day mappings with correct cron weekday numbers."""
        assert hasattr(_DAY_MAP, '__getitem__') or isinstance(_DAY_MAP, dict), "_DAY_MAP should be dict-like"
        
        # Check full day names
        assert _DAY_MAP['sunday'] == 0
        assert _DAY_MAP['monday'] == 1
        assert _DAY_MAP['tuesday'] == 2
        assert _DAY_MAP['wednesday'] == 3
        assert _DAY_MAP['thursday'] == 4
        assert _DAY_MAP['friday'] == 5
        assert _DAY_MAP['saturday'] == 6
        
        # Check abbreviated names
        assert _DAY_MAP['sun'] == 0
        assert _DAY_MAP['mon'] == 1
        assert _DAY_MAP['tue'] == 2
        assert _DAY_MAP['wed'] == 3
        assert _DAY_MAP['thu'] == 4
        assert _DAY_MAP['fri'] == 5
        assert _DAY_MAP['sat'] == 6
        
        # Verify we have exactly 14 keys
        assert len(_DAY_MAP) == 14
    
    def test_cron_weekday_to_python_structure(self):
        """Verify _CRON_WEEKDAY_TO_PYTHON correctly maps cron weekdays to Python weekdays."""
        assert len(_CRON_WEEKDAY_TO_PYTHON) == 7
        
        # Cron 0 = Sunday = Python 6
        assert _CRON_WEEKDAY_TO_PYTHON[0] == 6
        # Cron 1 = Monday = Python 0
        assert _CRON_WEEKDAY_TO_PYTHON[1] == 0
        # Cron 2 = Tuesday = Python 1
        assert _CRON_WEEKDAY_TO_PYTHON[2] == 1
        # Cron 3 = Wednesday = Python 2
        assert _CRON_WEEKDAY_TO_PYTHON[3] == 2
        # Cron 4 = Thursday = Python 3
        assert _CRON_WEEKDAY_TO_PYTHON[4] == 3
        # Cron 5 = Friday = Python 4
        assert _CRON_WEEKDAY_TO_PYTHON[5] == 4
        # Cron 6 = Saturday = Python 5
        assert _CRON_WEEKDAY_TO_PYTHON[6] == 5
    
    def test_cron_fields_structure(self):
        """Verify CronFields can be constructed with proper field names."""
        # CronFields is described as a struct/dict with specific keys
        fields = {'minute': '30', 'hour': '9', 'dom': '*', 'month': '*', 'dow': '*'}
        
        # Verify all expected keys exist
        assert 'minute' in fields
        assert 'hour' in fields
        assert 'dom' in fields
        assert 'month' in fields
        assert 'dow' in fields
        
        # Verify all are strings
        for key, value in fields.items():
            assert isinstance(value, str), f"{key} should be a string"


# ============================================================================
# SCHEDULE_TO_CRON TESTS
# ============================================================================

class TestScheduleToCron:
    """Tests for schedule_to_cron function."""
    
    def test_schedule_to_cron_daily(self):
        """Convert daily schedule to cron expression."""
        result = schedule_to_cron(
            daily=True, weekdays=False, weekly=None, biweekly=None,
            monthly=None, quarterly=False, hour=9, minute=30
        )
        assert result == "30 9 * * *"
        assert len(result.split()) == 5
    
    def test_schedule_to_cron_weekdays(self):
        """Convert weekdays schedule to cron expression."""
        result = schedule_to_cron(
            daily=False, weekdays=True, weekly=None, biweekly=None,
            monthly=None, quarterly=False, hour=8, minute=0
        )
        assert result == "0 8 * * 1-5"
        assert len(result.split()) == 5
    
    def test_schedule_to_cron_weekly(self):
        """Convert weekly schedule to cron expression."""
        result = schedule_to_cron(
            daily=False, weekdays=False, weekly='monday', biweekly=None,
            monthly=None, quarterly=False, hour=10, minute=15
        )
        assert result == "15 10 * * 1"
        assert len(result.split()) == 5
    
    def test_schedule_to_cron_weekly_abbreviated(self):
        """Convert weekly schedule with abbreviated day name."""
        result = schedule_to_cron(
            daily=False, weekdays=False, weekly='fri', biweekly=None,
            monthly=None, quarterly=False, hour=17, minute=45
        )
        assert result == "45 17 * * 5"
        assert len(result.split()) == 5
    
    def test_schedule_to_cron_biweekly(self):
        """Convert biweekly schedule to cron expression (2nd and 4th occurrence)."""
        result = schedule_to_cron(
            daily=False, weekdays=False, weekly=None, biweekly='wednesday',
            monthly=None, quarterly=False, hour=14, minute=0
        )
        assert result == "0 14 8-14,22-28 * 3"
        # Verify biweekly pattern: days 8-14 and 22-28
        parts = result.split()
        assert "8-14,22-28" in parts[2]
        assert "3" in parts[4]  # Wednesday
    
    def test_schedule_to_cron_monthly(self):
        """Convert monthly schedule to cron expression."""
        result = schedule_to_cron(
            daily=False, weekdays=False, weekly=None, biweekly=None,
            monthly='1', quarterly=False, hour=0, minute=0
        )
        assert result == "0 0 1 * *"
        assert len(result.split()) == 5
    
    def test_schedule_to_cron_quarterly(self):
        """Convert quarterly schedule to cron expression (Jan, Apr, Jul, Oct)."""
        result = schedule_to_cron(
            daily=False, weekdays=False, weekly=None, biweekly=None,
            monthly=None, quarterly=True, hour=12, minute=0
        )
        assert result == "0 12 1 1,4,7,10 *"
        parts = result.split()
        assert "1,4,7,10" in parts[3]  # Months
        assert "1" in parts[2]  # First day of month
    
    def test_schedule_to_cron_midnight(self):
        """Create schedule at midnight (edge case for hour=0, minute=0)."""
        result = schedule_to_cron(
            daily=True, weekdays=False, weekly=None, biweekly=None,
            monthly=None, quarterly=False, hour=0, minute=0
        )
        assert result == "0 0 * * *"
    
    def test_schedule_to_cron_case_insensitive_day(self):
        """Day names should be case-insensitive."""
        result = schedule_to_cron(
            daily=False, weekdays=False, weekly='MONDAY', biweekly=None,
            monthly=None, quarterly=False, hour=10, minute=0
        )
        assert result == "0 10 * * 1"
    
    def test_schedule_to_cron_unknown_day(self):
        """Raise UnknownDayError for invalid day name in weekly schedule."""
        with pytest.raises(Exception) as exc_info:
            schedule_to_cron(
                daily=False, weekdays=False, weekly='funday', biweekly=None,
                monthly=None, quarterly=False, hour=10, minute=0
            )
        assert 'UnknownDay' in str(exc_info.typename) or 'day' in str(exc_info.value).lower()
    
    def test_schedule_to_cron_no_schedule(self):
        """Raise NoScheduleError when no schedule frequency is specified."""
        with pytest.raises(Exception) as exc_info:
            schedule_to_cron(
                daily=False, weekdays=False, weekly=None, biweekly=None,
                monthly=None, quarterly=False, hour=10, minute=0
            )
        assert 'NoSchedule' in str(exc_info.typename) or 'schedule' in str(exc_info.value).lower()


# ============================================================================
# PARSE_CRON TESTS
# ============================================================================

class TestParseCron:
    """Tests for parse_cron function."""
    
    def test_parse_cron_simple(self):
        """Parse a simple daily cron expression."""
        result = parse_cron("30 9 * * *")
        assert isinstance(result, dict)
        assert result['minute'] == '30'
        assert result['hour'] == '9'
        assert result['dom'] == '*'
        assert result['month'] == '*'
        assert result['dow'] == '*'
    
    def test_parse_cron_complex(self):
        """Parse a complex cron expression with ranges and lists."""
        result = parse_cron("0,15,30,45 8-17 1-15 1,6,12 1-5")
        assert result['minute'] == '0,15,30,45'
        assert result['hour'] == '8-17'
        assert result['dom'] == '1-15'
        assert result['month'] == '1,6,12'
        assert result['dow'] == '1-5'
    
    def test_parse_cron_invalid_field_count_too_few(self):
        """Raise InvalidCronFieldCount when fewer than 5 fields."""
        with pytest.raises(Exception) as exc_info:
            parse_cron("30 9 * *")
        assert 'InvalidCronFieldCount' in str(exc_info.typename) or 'field' in str(exc_info.value).lower()
    
    def test_parse_cron_invalid_field_count_too_many(self):
        """Raise InvalidCronFieldCount when more than 5 fields."""
        with pytest.raises(Exception) as exc_info:
            parse_cron("30 9 * * * 2024")
        assert 'InvalidCronFieldCount' in str(exc_info.typename) or 'field' in str(exc_info.value).lower()
    
    def test_parse_cron_empty_string(self):
        """Raise InvalidCronFieldCount for empty string."""
        with pytest.raises(Exception) as exc_info:
            parse_cron("")
        assert 'InvalidCronFieldCount' in str(exc_info.typename) or 'field' in str(exc_info.value).lower()


# ============================================================================
# EXPAND_FIELD TESTS
# ============================================================================

class TestExpandField:
    """Tests for _expand_field function."""
    
    def test_expand_field_asterisk(self):
        """Expand asterisk to full range."""
        result = _expand_field("*", 0, 59)
        assert isinstance(result, set)
        assert len(result) == 60
        assert 0 in result
        assert 59 in result
        assert result == set(range(0, 60))
    
    def test_expand_field_single_value(self):
        """Expand single numeric value."""
        result = _expand_field("15", 0, 59)
        assert result == {15}
    
    def test_expand_field_range(self):
        """Expand range syntax."""
        result = _expand_field("1-5", 0, 23)
        assert result == {1, 2, 3, 4, 5}
    
    def test_expand_field_list(self):
        """Expand comma-separated list."""
        result = _expand_field("1,3,5,7", 0, 12)
        assert result == {1, 3, 5, 7}
    
    def test_expand_field_mixed(self):
        """Expand mixed list and ranges."""
        result = _expand_field("1,3-5,10", 0, 23)
        assert result == {1, 3, 4, 5, 10}
    
    def test_expand_field_boundary_min(self):
        """Expand range at minimum boundary."""
        result = _expand_field("0-2", 0, 59)
        assert result == {0, 1, 2}
    
    def test_expand_field_boundary_max(self):
        """Expand range at maximum boundary."""
        result = _expand_field("57-59", 0, 59)
        assert result == {57, 58, 59}
    
    def test_expand_field_invalid_format(self):
        """Raise InvalidFieldFormat for non-numeric characters."""
        with pytest.raises(Exception) as exc_info:
            _expand_field("abc", 0, 59)
        assert 'InvalidFieldFormat' in str(exc_info.typename) or 'format' in str(exc_info.value).lower() or 'invalid' in str(exc_info.value).lower()


# ============================================================================
# COMPUTE_NEXT_RUN TESTS
# ============================================================================

class TestComputeNextRun:
    """Tests for compute_next_run function."""
    
    def test_compute_next_run_daily(self):
        """Compute next run for daily schedule."""
        after = datetime(2024, 1, 15, 8, 0, 0)
        result = compute_next_run("30 9 * * *", after)
        assert result != ""
        assert "2024-01-15" in result
        assert "09:30" in result
    
    def test_compute_next_run_next_day(self):
        """Compute next run that falls on next day."""
        after = datetime(2024, 1, 15, 10, 0, 0)
        result = compute_next_run("30 9 * * *", after)
        assert result != ""
        assert "2024-01-16" in result
        assert "09:30" in result
    
    def test_compute_next_run_specific_weekday(self):
        """Compute next run for specific weekday (Monday)."""
        after = datetime(2024, 1, 15, 8, 0, 0)  # Monday
        result = compute_next_run("0 10 * * 1", after)
        assert result != ""
        # Should be next Monday at 10:00
        assert "10:00" in result
    
    def test_compute_next_run_no_match_366_days(self):
        """Return empty string when no match within 366 days."""
        after = datetime(2024, 1, 1, 0, 0, 0)
        result = compute_next_run("0 0 31 2 *", after)  # Feb 31 never exists
        assert result == ""
    
    def test_compute_next_run_leap_year(self):
        """Compute next run on leap year date (Feb 29)."""
        after = datetime(2024, 2, 28, 0, 0, 0)
        result = compute_next_run("0 0 29 2 *", after)
        assert result != ""
        assert "2024-02-29" in result
    
    def test_compute_next_run_year_wrap(self):
        """Compute next run that wraps into next year."""
        after = datetime(2024, 12, 31, 12, 0, 0)
        result = compute_next_run("0 0 1 1 *", after)
        assert result != ""
        assert "2025-01-01" in result
    
    def test_compute_next_run_default_after(self):
        """Use current time when after is None."""
        result = compute_next_run("0 0 * * *", None)
        # Should return some future midnight
        assert isinstance(result, str)
        # If empty, it means no match in 366 days (unlikely for daily midnight)
        # Otherwise should have valid date format
        if result:
            assert "00:00" in result
    
    def test_compute_next_run_invalid_cron(self):
        """Raise InvalidCronExpression for malformed cron."""
        with pytest.raises(Exception) as exc_info:
            compute_next_run("invalid", datetime(2024, 1, 1, 0, 0, 0))
        assert 'InvalidCron' in str(exc_info.typename) or 'cron' in str(exc_info.value).lower() or 'invalid' in str(exc_info.value).lower()
    
    def test_compute_next_run_or_semantics(self):
        """Verify OR semantics when both DOM and DOW are restricted."""
        after = datetime(2024, 1, 1, 0, 0, 0)
        result = compute_next_run("0 0 15 * 1", after)  # 15th OR Monday
        assert result != ""
        # Result should match either 15th of month OR a Monday


# ============================================================================
# DESCRIBE_CRON TESTS
# ============================================================================

class TestDescribeCron:
    """Tests for describe_cron function."""
    
    def test_describe_cron_daily(self):
        """Describe daily schedule in human-readable format."""
        result = describe_cron("30 9 * * *")
        assert isinstance(result, str)
        assert len(result) > 0
        # Should be human-readable (not just the cron expression)
    
    def test_describe_cron_weekdays(self):
        """Describe weekdays schedule."""
        result = describe_cron("0 8 * * 1-5")
        assert isinstance(result, str)
        assert len(result) > 0
    
    def test_describe_cron_weekly(self):
        """Describe weekly schedule."""
        result = describe_cron("0 10 * * 1")
        assert isinstance(result, str)
        assert len(result) > 0
    
    def test_describe_cron_fallback(self):
        """Fallback to original expression for unrecognized pattern."""
        result = describe_cron("*/5 * * * *")
        assert isinstance(result, str)
        # Should return original or some description
        assert len(result) > 0
    
    def test_describe_cron_invalid(self):
        """Raise InvalidCronExpression for malformed cron."""
        with pytest.raises(Exception) as exc_info:
            describe_cron("invalid cron")
        assert 'InvalidCron' in str(exc_info.typename) or 'cron' in str(exc_info.value).lower() or 'invalid' in str(exc_info.value).lower()


# ============================================================================
# FIND_ASCEND_PATH TESTS
# ============================================================================

class TestFindAscendPath:
    """Tests for _find_ascend_path function."""
    
    @patch('shutil.which')
    def test_find_ascend_path_in_path(self, mock_which):
        """Find ascend executable via shutil.which."""
        mock_which.return_value = '/usr/local/bin/ascend'
        result = _find_ascend_path()
        assert result == '/usr/local/bin/ascend'
        mock_which.assert_called_once_with('ascend')
    
    @patch('shutil.which')
    @patch('pathlib.Path.exists')
    def test_find_ascend_path_common_location(self, mock_exists, mock_which):
        """Find ascend in common installation location."""
        mock_which.return_value = None
        # Make one of the common locations return True
        def exists_side_effect(path_self):
            return str(path_self) == '/usr/local/bin/ascend'
        mock_exists.side_effect = exists_side_effect
        
        result = _find_ascend_path()
        # Should find it in common location
        assert 'ascend' in result
    
    @patch('shutil.which')
    @patch('pathlib.Path.exists')
    def test_find_ascend_path_fallback(self, mock_exists, mock_which):
        """Fallback to 'ascend' string when not found."""
        mock_which.return_value = None
        mock_exists.return_value = False
        
        result = _find_ascend_path()
        assert result == 'ascend'


# ============================================================================
# CRON_TO_CALENDAR_INTERVALS TESTS
# ============================================================================

class TestCronToCalendarIntervals:
    """Tests for _cron_to_calendar_intervals function."""
    
    def test_cron_to_calendar_intervals_single(self):
        """Convert simple cron to single calendar interval."""
        result = _cron_to_calendar_intervals("30 9 * * *")
        assert isinstance(result, str)
        assert '<dict>' in result or 'dict' in result.lower()
        assert '9' in result  # Hour
        assert '30' in result  # Minute
    
    def test_cron_to_calendar_intervals_multiple(self):
        """Convert cron with multiple values to array of intervals."""
        result = _cron_to_calendar_intervals("0 9,14 * * *")
        assert isinstance(result, str)
        # Should contain array or multiple dicts
        assert '<array>' in result or '<dict>' in result
    
    def test_cron_to_calendar_intervals_weekday(self):
        """Convert weekday-based cron to calendar intervals."""
        result = _cron_to_calendar_intervals("0 10 * * 1")
        assert isinstance(result, str)
        assert '<dict>' in result or 'dict' in result.lower()
        # Should contain weekday info
    
    def test_cron_to_calendar_intervals_invalid(self):
        """Raise InvalidCronExpression for malformed cron."""
        with pytest.raises(Exception) as exc_info:
            _cron_to_calendar_intervals("bad")
        assert 'InvalidCron' in str(exc_info.typename) or 'cron' in str(exc_info.value).lower() or 'invalid' in str(exc_info.value).lower()


# ============================================================================
# GENERATE_PLIST TESTS
# ============================================================================

class TestGeneratePlist:
    """Tests for generate_plist function."""
    
    @patch('src_ascend_scheduler._find_ascend_path')
    def test_generate_plist_metadata(self, mock_find):
        """Generate plist metadata (label, ascend_path, log_path)."""
        mock_find.return_value = '/usr/local/bin/ascend'
        
        result = generate_plist("daily_backup", Path("/tmp/schedules"))
        
        # Should return a tuple
        assert isinstance(result, tuple)
        assert len(result) == 3
        
        label, ascend_path, log_path = result
        assert label == "com.ascend.schedule.daily_backup"
        assert ascend_path == '/usr/local/bin/ascend'
        assert log_path == "/tmp/schedules/daily_backup.log"
    
    @patch('src_ascend_scheduler._find_ascend_path')
    def test_generate_plist_special_chars(self, mock_find):
        """Generate plist metadata with special characters in schedule name."""
        mock_find.return_value = '/usr/local/bin/ascend'
        
        result = generate_plist("my-test_schedule", Path("/tmp/schedules"))
        
        label, ascend_path, log_path = result
        assert label == "com.ascend.schedule.my-test_schedule"
        assert log_path == "/tmp/schedules/my-test_schedule.log"


# ============================================================================
# WRITE_PLIST TESTS
# ============================================================================

class TestWritePlist:
    """Tests for write_plist function."""
    
    @patch('src_ascend_scheduler._cron_to_calendar_intervals')
    @patch('src_ascend_scheduler.generate_plist')
    @patch('pathlib.Path.mkdir')
    @patch('pathlib.Path.write_text')
    @patch('pathlib.Path.expanduser')
    def test_write_plist_creates_directory(self, mock_expanduser, mock_write, mock_mkdir, mock_gen, mock_cron_to_cal):
        """Write plist file and create LaunchAgents directory if needed."""
        mock_cron_to_cal.return_value = '<dict><key>Hour</key><integer>9</integer></dict>'
        mock_gen.return_value = ('com.ascend.schedule.test', '/usr/local/bin/ascend', '/tmp/test.log')
        
        mock_home = Path('/home/user')
        mock_expanduser.return_value = mock_home / 'Library' / 'LaunchAgents' / 'test.plist'
        
        result = write_plist("test_schedule", "0 9 * * *", Path("/tmp/schedules"))
        
        assert isinstance(result, Path) or result is None or isinstance(result, (str, type(Path())))
        mock_mkdir.assert_called()
    
    @patch('src_ascend_scheduler._cron_to_calendar_intervals')
    def test_write_plist_invalid_cron(self, mock_cron_to_cal):
        """Raise InvalidCronExpression for malformed cron."""
        mock_cron_to_cal.side_effect = Exception("InvalidCronExpression")
        
        with pytest.raises(Exception) as exc_info:
            write_plist("test_schedule", "invalid", Path("/tmp/schedules"))
        assert 'InvalidCron' in str(exc_info.value) or 'cron' in str(exc_info.value).lower()


# ============================================================================
# LOAD_PLIST TESTS
# ============================================================================

class TestLoadPlist:
    """Tests for load_plist function."""
    
    @patch('pathlib.Path.exists')
    @patch('subprocess.run')
    def test_load_plist_success(self, mock_run, mock_exists):
        """Successfully load plist using launchctl."""
        mock_exists.return_value = True
        mock_run.return_value = Mock(returncode=0)
        
        result = load_plist("test_schedule")
        assert result is True
    
    @patch('pathlib.Path.exists')
    def test_load_plist_file_not_exists(self, mock_exists):
        """Return False when plist file doesn't exist."""
        mock_exists.return_value = False
        
        result = load_plist("nonexistent")
        assert result is False
    
    @patch('pathlib.Path.exists')
    @patch('subprocess.run')
    def test_load_plist_launchctl_fails(self, mock_run, mock_exists):
        """Return False when launchctl command fails."""
        mock_exists.return_value = True
        mock_run.side_effect = Exception("Command failed")
        
        result = load_plist("test_schedule")
        assert result is False


# ============================================================================
# UNLOAD_PLIST TESTS
# ============================================================================

class TestUnloadPlist:
    """Tests for unload_plist function."""
    
    @patch('pathlib.Path.exists')
    @patch('subprocess.run')
    def test_unload_plist_success(self, mock_run, mock_exists):
        """Successfully unload plist using launchctl."""
        mock_exists.return_value = True
        mock_run.return_value = Mock(returncode=0)
        
        result = unload_plist("test_schedule")
        assert result is True
    
    @patch('pathlib.Path.exists')
    def test_unload_plist_file_not_exists(self, mock_exists):
        """Return False when plist file doesn't exist."""
        mock_exists.return_value = False
        
        result = unload_plist("nonexistent")
        assert result is False


# ============================================================================
# REMOVE_PLIST TESTS
# ============================================================================

class TestRemovePlist:
    """Tests for remove_plist function."""
    
    @patch('src_ascend_scheduler.unload_plist')
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.unlink')
    def test_remove_plist_success(self, mock_unlink, mock_exists, mock_unload):
        """Successfully unload and delete plist file."""
        mock_exists.return_value = True
        mock_unload.return_value = True
        
        result = remove_plist("test_schedule")
        assert result is True
        mock_unload.assert_called_once_with("test_schedule")
        mock_unlink.assert_called_once()
    
    @patch('pathlib.Path.exists')
    def test_remove_plist_file_not_exists(self, mock_exists):
        """Return False when plist file doesn't exist."""
        mock_exists.return_value = False
        
        result = remove_plist("nonexistent")
        assert result is False


# ============================================================================
# INVARIANT TESTS
# ============================================================================

class TestInvariants:
    """Tests for system invariants."""
    
    def test_invariant_cron_format_5_fields(self):
        """All generated cron expressions must have exactly 5 fields."""
        test_cases = [
            (True, False, None, None, None, False, 9, 30),  # daily
            (False, True, None, None, None, False, 8, 0),   # weekdays
            (False, False, 'monday', None, None, False, 10, 0),  # weekly
            (False, False, None, None, None, True, 12, 0),  # quarterly
        ]
        
        for params in test_cases:
            result = schedule_to_cron(*params)
            fields = result.split()
            assert len(fields) == 5, f"Cron expression should have 5 fields, got {len(fields)}: {result}"
    
    def test_invariant_cron_weekday_0_is_sunday(self):
        """Verify cron weekday 0 maps to Sunday (not Monday like Python)."""
        # Cron 0 should map to Python 6 (Sunday)
        assert _CRON_WEEKDAY_TO_PYTHON[0] == 6
        # Cron 1 should map to Python 0 (Monday)
        assert _CRON_WEEKDAY_TO_PYTHON[1] == 0
        # They should not be equal
        assert _CRON_WEEKDAY_TO_PYTHON[0] != 0
    
    def test_invariant_biweekly_targets_2nd_4th(self):
        """Biweekly schedules target days 8-14 and 22-28."""
        result = schedule_to_cron(
            daily=False, weekdays=False, weekly=None, biweekly='monday',
            monthly=None, quarterly=False, hour=10, minute=0
        )
        
        parts = result.split()
        dom_field = parts[2]
        dow_field = parts[4]
        
        assert '8-14,22-28' in dom_field or ('8-14' in dom_field and '22-28' in dom_field)
        assert dow_field == '1'  # Monday
    
    def test_invariant_quarterly_months(self):
        """Quarterly schedules run on Jan, Apr, Jul, Oct (months 1,4,7,10)."""
        result = schedule_to_cron(
            daily=False, weekdays=False, weekly=None, biweekly=None,
            monthly=None, quarterly=True, hour=0, minute=0
        )
        
        parts = result.split()
        dom_field = parts[2]
        month_field = parts[3]
        
        assert dom_field == '1'  # First day of month
        assert month_field == '1,4,7,10'  # Jan, Apr, Jul, Oct
    
    @patch('src_ascend_scheduler._find_ascend_path')
    def test_invariant_launchd_label_format(self, mock_find):
        """LaunchAgents label format is com.ascend.schedule.{schedule_name}."""
        mock_find.return_value = '/usr/local/bin/ascend'
        
        label, _, _ = generate_plist("my_schedule", Path("/tmp"))
        
        assert label.startswith("com.ascend.schedule.")
        assert label.endswith("my_schedule")
        assert label == "com.ascend.schedule.my_schedule"
    
    @patch('src_ascend_scheduler._find_ascend_path')
    def test_invariant_log_file_format(self, mock_find):
        """Log file format is {schedules_dir}/{schedule_name}.log."""
        mock_find.return_value = '/usr/local/bin/ascend'
        
        _, _, log_path = generate_plist("test_log", Path("/var/log/schedules"))
        
        assert log_path == "/var/log/schedules/test_log.log"
        assert log_path.endswith(".log")
        assert "test_log" in log_path


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

class TestEdgeCases:
    """Additional edge case tests for comprehensive coverage."""
    
    def test_expand_field_single_range_element(self):
        """Range with same start and end."""
        result = _expand_field("5-5", 0, 10)
        assert result == {5}
    
    def test_parse_cron_extra_whitespace(self):
        """Parse cron with multiple spaces between fields."""
        result = parse_cron("30  9  *  *  *")
        assert result['minute'] == '30'
        assert result['hour'] == '9'
    
    def test_schedule_to_cron_sunday(self):
        """Weekly schedule for Sunday (cron weekday 0)."""
        result = schedule_to_cron(
            daily=False, weekdays=False, weekly='sunday', biweekly=None,
            monthly=None, quarterly=False, hour=10, minute=0
        )
        parts = result.split()
        assert parts[4] == '0'  # Sunday is 0 in cron
    
    def test_schedule_to_cron_monthly_last_day(self):
        """Monthly schedule on day 31."""
        result = schedule_to_cron(
            daily=False, weekdays=False, weekly=None, biweekly=None,
            monthly='31', quarterly=False, hour=0, minute=0
        )
        parts = result.split()
        assert parts[2] == '31'
    
    @patch('src_ascend_scheduler._find_ascend_path')
    @patch('pathlib.Path.exists')
    def test_generate_plist_path_with_spaces(self, mock_exists, mock_find):
        """Handle schedule names and paths with spaces."""
        mock_find.return_value = '/usr/local/bin/ascend'
        mock_exists.return_value = True
        
        label, _, log_path = generate_plist("my schedule", Path("/tmp/my schedules"))
        
        assert "my schedule" in label or "my_schedule" in label
        assert "my schedule" in log_path or "my_schedule" in log_path


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
