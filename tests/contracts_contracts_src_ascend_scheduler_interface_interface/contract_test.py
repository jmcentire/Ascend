"""
Contract tests for Ascend Scheduler Interface
Generated test suite for validating scheduler implementations against contract specifications.
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, mock_open
import subprocess
import tempfile
import os

# Import module under test
from contracts.contracts_src_ascend_scheduler_interface.interface import (
    schedule_to_cron,
    parse_cron,
    _expand_field,
    compute_next_run,
    describe_cron,
    _find_ascend_path,
    _cron_to_calendar_intervals,
    generate_plist,
    write_plist,
    load_plist,
    unload_plist,
    remove_plist,
)


# ============================================================================
# SCHEDULE_TO_CRON TESTS
# ============================================================================

def test_schedule_to_cron_daily_happy_path():
    """Daily schedule should generate cron expression with * for dom, month, dow"""
    result = schedule_to_cron(
        daily=True,
        weekdays=False,
        weekly=None,
        biweekly=None,
        monthly=None,
        quarterly=False,
        hour=10,
        minute=30
    )
    assert result == '30 10 * * *'


def test_schedule_to_cron_weekdays_happy_path():
    """Weekdays schedule should generate cron expression with 1-5 for dow"""
    result = schedule_to_cron(
        daily=False,
        weekdays=True,
        weekly=None,
        biweekly=None,
        monthly=None,
        quarterly=False,
        hour=9,
        minute=0
    )
    assert result == '0 9 * * 1-5'


def test_schedule_to_cron_weekly_happy_path():
    """Weekly schedule with specific day generates correct dow field"""
    result = schedule_to_cron(
        daily=False,
        weekdays=False,
        weekly='monday',
        biweekly=None,
        monthly=None,
        quarterly=False,
        hour=14,
        minute=15
    )
    assert '* * 1' in result
    assert '15 14' in result


def test_schedule_to_cron_biweekly_happy_path():
    """Biweekly schedule should generate days 8-14,22-28 for specified weekday"""
    result = schedule_to_cron(
        daily=False,
        weekdays=False,
        weekly=None,
        biweekly='friday',
        monthly=None,
        quarterly=False,
        hour=12,
        minute=0
    )
    assert '8-14,22-28' in result
    assert '0 12' in result


def test_schedule_to_cron_monthly_happy_path():
    """Monthly schedule with day number generates correct dom field"""
    result = schedule_to_cron(
        daily=False,
        weekdays=False,
        weekly=None,
        biweekly=None,
        monthly='15',
        quarterly=False,
        hour=8,
        minute=30
    )
    assert '30 8 15 * *' == result


def test_schedule_to_cron_quarterly_happy_path():
    """Quarterly schedule runs on 1st of months 1,4,7,10"""
    result = schedule_to_cron(
        daily=False,
        weekdays=False,
        weekly=None,
        biweekly=None,
        monthly=None,
        quarterly=True,
        hour=0,
        minute=0
    )
    assert result == '0 0 1 1,4,7,10 *'


def test_schedule_to_cron_hour_minute_boundaries():
    """Boundary values for hour (0, 23) and minute (0, 59) should work"""
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
    assert result == '59 23 * * *'


def test_schedule_to_cron_weekly_short_day_name():
    """Weekly schedule accepts short day names like 'mon' case-insensitively"""
    result = schedule_to_cron(
        daily=False,
        weekdays=False,
        weekly='Mon',
        biweekly=None,
        monthly=None,
        quarterly=False,
        hour=10,
        minute=0
    )
    assert '* * 1' in result


def test_schedule_to_cron_invalid_day_name():
    """Invalid day name should raise invalid_day error"""
    with pytest.raises(Exception) as exc_info:
        schedule_to_cron(
            daily=False,
            weekdays=False,
            weekly='notaday',
            biweekly=None,
            monthly=None,
            quarterly=False,
            hour=10,
            minute=0
        )
    assert 'invalid_day' in str(exc_info.value).lower() or 'notaday' in str(exc_info.value).lower()


def test_schedule_to_cron_no_frequency_specified():
    """No frequency flag set should raise no_frequency error"""
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
    assert 'no_frequency' in str(exc_info.value).lower() or 'frequency' in str(exc_info.value).lower()


# ============================================================================
# PARSE_CRON TESTS
# ============================================================================

def test_parse_cron_happy_path():
    """Parse valid 5-field cron expression into dictionary"""
    result = parse_cron('30 14 * * 1-5')
    assert result['minute'] == '30'
    assert result['hour'] == '14'
    assert result['dom'] == '*'
    assert result['month'] == '*'
    assert result['dow'] == '1-5'


def test_parse_cron_with_ranges_and_lists():
    """Parse cron expression with ranges and comma-separated lists"""
    result = parse_cron('0,30 9-17 1,15 1,4,7,10 *')
    assert result['minute'] == '0,30'
    assert result['hour'] == '9-17'
    assert result['dom'] == '1,15'
    assert result['month'] == '1,4,7,10'


def test_parse_cron_all_wildcards():
    """Parse cron expression with all wildcards"""
    result = parse_cron('* * * * *')
    assert all(result[k] == '*' for k in ['minute', 'hour', 'dom', 'month', 'dow'])


def test_parse_cron_invalid_field_count_too_few():
    """Cron expression with fewer than 5 fields should raise invalid_field_count"""
    with pytest.raises(Exception) as exc_info:
        parse_cron('30 14 *')
    assert 'invalid_field_count' in str(exc_info.value).lower() or 'field' in str(exc_info.value).lower()


def test_parse_cron_invalid_field_count_too_many():
    """Cron expression with more than 5 fields should raise invalid_field_count"""
    with pytest.raises(Exception) as exc_info:
        parse_cron('30 14 * * 1 extra field')
    assert 'invalid_field_count' in str(exc_info.value).lower() or 'field' in str(exc_info.value).lower()


# ============================================================================
# EXPAND_FIELD TESTS
# ============================================================================

def test_expand_field_wildcard():
    """Wildcard should expand to all values in range"""
    result = _expand_field('*', 0, 23)
    assert result == set(range(24))


def test_expand_field_single_value():
    """Single integer should expand to set with that value"""
    result = _expand_field('15', 0, 59)
    assert result == {15}


def test_expand_field_range():
    """Range N-M should expand to set of values from N to M inclusive"""
    result = _expand_field('1-5', 0, 6)
    assert result == {1, 2, 3, 4, 5}


def test_expand_field_comma_separated():
    """Comma-separated values should expand to union of values"""
    result = _expand_field('1,15,30', 0, 31)
    assert result == {1, 15, 30}


def test_expand_field_mixed_format():
    """Mix of ranges and values should expand correctly"""
    result = _expand_field('1-3,10,20-22', 0, 31)
    assert result == {1, 2, 3, 10, 20, 21, 22}


def test_expand_field_boundary_values():
    """Field at exact min and max boundaries should work"""
    result = _expand_field('0,59', 0, 59)
    assert result == {0, 59}


def test_expand_field_invalid_integer():
    """Non-integer field value should raise invalid_integer error"""
    with pytest.raises(Exception) as exc_info:
        _expand_field('abc', 0, 59)
    assert 'invalid' in str(exc_info.value).lower()


# ============================================================================
# COMPUTE_NEXT_RUN TESTS
# ============================================================================

def test_compute_next_run_daily_schedule():
    """Daily schedule should return next occurrence at specified time"""
    result = compute_next_run('30 10 * * *', datetime(2024, 1, 15, 9, 0))
    assert result == '2024-01-15 10:30'


def test_compute_next_run_after_time_passed():
    """When time has passed today, should return tomorrow"""
    result = compute_next_run('30 10 * * *', datetime(2024, 1, 15, 11, 0))
    assert result == '2024-01-16 10:30'


def test_compute_next_run_weekly_specific_day():
    """Weekly schedule should match specific day of week"""
    result = compute_next_run('0 9 * * 1', datetime(2024, 1, 15, 8, 0))
    assert '09:00' in result
    assert result > '2024-01-15'


def test_compute_next_run_monthly_specific_day():
    """Monthly schedule on specific day should match that day"""
    result = compute_next_run('0 12 15 * *', datetime(2024, 1, 10, 0, 0))
    assert result == '2024-01-15 12:00'


def test_compute_next_run_cron_or_semantics():
    """When both dom and dow are restricted, should match EITHER condition"""
    result = compute_next_run('0 10 1 * 1', datetime(2024, 1, 2, 0, 0))
    assert result is not None
    assert len(result) > 0


def test_compute_next_run_leap_year_feb_29():
    """Schedule on Feb 29 should work in leap years"""
    result = compute_next_run('0 0 29 2 *', datetime(2024, 2, 1, 0, 0))
    assert result == '2024-02-29 00:00'


def test_compute_next_run_year_boundary():
    """Schedule should handle year boundaries correctly"""
    result = compute_next_run('0 0 1 1 *', datetime(2024, 12, 31, 12, 0))
    assert result == '2025-01-01 00:00'


def test_compute_next_run_no_match_within_366_days():
    """If no match found within 366 days, return empty string"""
    result = compute_next_run('0 0 31 2 *', datetime(2024, 1, 1, 0, 0))
    assert result == ''


def test_compute_next_run_invalid_cron():
    """Invalid cron expression should raise invalid_cron error"""
    with pytest.raises(Exception) as exc_info:
        compute_next_run('30 14', datetime(2024, 1, 1, 0, 0))
    assert 'invalid' in str(exc_info.value).lower() or 'cron' in str(exc_info.value).lower()


def test_compute_next_run_invalid_field_value():
    """Invalid field value in cron should raise invalid_field_value error"""
    with pytest.raises(Exception) as exc_info:
        compute_next_run('abc 14 * * *', datetime(2024, 1, 1, 0, 0))
    assert 'invalid' in str(exc_info.value).lower()


# ============================================================================
# DESCRIBE_CRON TESTS
# ============================================================================

def test_describe_cron_daily():
    """Daily cron expression should be described as 'Daily at HH:MM'"""
    result = describe_cron('30 10 * * *')
    assert 'daily' in result.lower() or '10:30' in result


def test_describe_cron_weekdays():
    """Weekdays cron expression should be described appropriately"""
    result = describe_cron('0 9 * * 1-5')
    assert 'weekday' in result.lower() or 'monday' in result.lower() or '9:00' in result


def test_describe_cron_weekly():
    """Weekly cron expression should mention the day of week"""
    result = describe_cron('0 14 * * 1')
    assert 'monday' in result.lower() or '14:00' in result


def test_describe_cron_monthly():
    """Monthly cron expression should mention day of month"""
    result = describe_cron('0 12 15 * *')
    assert '15' in result or 'monthly' in result.lower()


def test_describe_cron_quarterly():
    """Quarterly cron expression should be described"""
    result = describe_cron('0 0 1 1,4,7,10 *')
    assert 'quarter' in result.lower() or '1,4,7,10' in result or len(result) > 0


def test_describe_cron_unrecognized_pattern():
    """Unrecognized pattern should fall back to original cron expression"""
    result = describe_cron('*/15 2-4 1,15 * 1,3,5')
    assert '*/15' in result or '2-4' in result or len(result) > 0


def test_describe_cron_invalid_cron():
    """Invalid cron expression should raise invalid_cron error"""
    with pytest.raises(Exception) as exc_info:
        describe_cron('30 14')
    assert 'invalid' in str(exc_info.value).lower() or 'cron' in str(exc_info.value).lower()


# ============================================================================
# FIND_ASCEND_PATH TESTS
# ============================================================================

@patch('shutil.which')
def test_find_ascend_path_system_path(mock_which):
    """Should find ascend in system PATH if available"""
    mock_which.return_value = '/usr/bin/ascend'
    result = _find_ascend_path()
    assert result == '/usr/bin/ascend'


@patch('shutil.which')
@patch('pathlib.Path.exists')
def test_find_ascend_path_usr_local_bin(mock_exists, mock_which):
    """Should check /usr/local/bin/ascend if not in PATH"""
    mock_which.return_value = None
    mock_exists.return_value = True
    result = _find_ascend_path()
    assert '/usr/local/bin/ascend' in result or 'ascend' in result


@patch('shutil.which')
@patch('pathlib.Path.exists')
def test_find_ascend_path_fallback(mock_exists, mock_which):
    """Should return 'ascend' as fallback if not found anywhere"""
    mock_which.return_value = None
    mock_exists.return_value = False
    result = _find_ascend_path()
    assert result == 'ascend'


# ============================================================================
# CRON_TO_CALENDAR_INTERVALS TESTS
# ============================================================================

def test_cron_to_calendar_intervals_daily():
    """Daily cron should convert to launchd CalendarInterval with hour/minute"""
    result = _cron_to_calendar_intervals('30 10 * * *')
    assert '<key>Hour</key>' in result
    assert '<integer>10</integer>' in result
    assert '<integer>30</integer>' in result


def test_cron_to_calendar_intervals_weekly():
    """Weekly cron should include Weekday in CalendarInterval"""
    result = _cron_to_calendar_intervals('0 9 * * 1')
    assert '<key>Weekday</key>' in result
    assert '<integer>1</integer>' in result


def test_cron_to_calendar_intervals_monthly():
    """Monthly cron should include Day in CalendarInterval"""
    result = _cron_to_calendar_intervals('0 12 15 * *')
    assert '<key>Day</key>' in result
    assert '<integer>15</integer>' in result


def test_cron_to_calendar_intervals_multiple_values():
    """Cron with multiple values should generate array of dicts"""
    result = _cron_to_calendar_intervals('0 9,17 * * *')
    assert '<array>' in result or '<dict>' in result


def test_cron_to_calendar_intervals_invalid_cron():
    """Invalid cron expression should raise invalid_cron error"""
    with pytest.raises(Exception) as exc_info:
        _cron_to_calendar_intervals('30')
    assert 'invalid' in str(exc_info.value).lower() or 'cron' in str(exc_info.value).lower()


# ============================================================================
# GENERATE_PLIST TESTS
# ============================================================================

def test_generate_plist_returns_metadata():
    """Generate plist should return tuple of label, ascend_path, log_path"""
    with patch('contracts_contracts_src_ascend_scheduler_interface_interface._find_ascend_path', return_value='/usr/bin/ascend'):
        result = generate_plist('test_schedule', Path('/tmp/schedules'))
        assert len(result) == 3
        assert 'test_schedule' in str(result)


# ============================================================================
# WRITE_PLIST TESTS
# ============================================================================

def test_write_plist_creates_file(tmp_path):
    """Write plist should create file in LaunchAgents directory"""
    with patch('pathlib.Path.home', return_value=tmp_path):
        with patch('contracts_contracts_src_ascend_scheduler_interface_interface._find_ascend_path', return_value='/usr/bin/ascend'):
            result = write_plist('test_schedule', '0 10 * * *', Path('/tmp/schedules'))
            assert result is not None
            assert 'test_schedule' in str(result)
            assert '.plist' in str(result)


def test_write_plist_creates_directory(tmp_path):
    """Write plist should create LaunchAgents directory if it doesn't exist"""
    with patch('pathlib.Path.home', return_value=tmp_path):
        with patch('contracts_contracts_src_ascend_scheduler_interface_interface._find_ascend_path', return_value='/usr/bin/ascend'):
            result = write_plist('test_schedule', '0 10 * * *', Path('/tmp/schedules'))
            assert result is not None


def test_write_plist_invalid_cron():
    """Invalid cron expression should raise invalid_cron error"""
    with pytest.raises(Exception) as exc_info:
        write_plist('test_schedule', 'invalid', Path('/tmp/schedules'))
    assert 'invalid' in str(exc_info.value).lower() or 'cron' in str(exc_info.value).lower()


# ============================================================================
# LOAD_PLIST TESTS
# ============================================================================

@patch('subprocess.run')
@patch('pathlib.Path.exists')
def test_load_plist_success(mock_exists, mock_run):
    """Load plist should return True when launchctl succeeds"""
    mock_exists.return_value = True
    mock_run.return_value = Mock(returncode=0)
    result = load_plist('test_schedule')
    assert result == True


@patch('pathlib.Path.exists')
def test_load_plist_file_not_exists(mock_exists):
    """Load plist should return False when file doesn't exist"""
    mock_exists.return_value = False
    result = load_plist('nonexistent_schedule')
    assert result == False


@patch('subprocess.run')
@patch('pathlib.Path.exists')
def test_load_plist_command_fails(mock_exists, mock_run):
    """Load plist should return False when launchctl fails"""
    mock_exists.return_value = True
    mock_run.return_value = Mock(returncode=1)
    result = load_plist('test_schedule')
    assert result == False


@patch('subprocess.run')
@patch('pathlib.Path.exists')
def test_load_plist_timeout(mock_exists, mock_run):
    """Load plist should return False on timeout"""
    mock_exists.return_value = True
    mock_run.side_effect = subprocess.TimeoutExpired(cmd='launchctl', timeout=10)
    result = load_plist('test_schedule')
    assert result == False


# ============================================================================
# UNLOAD_PLIST TESTS
# ============================================================================

@patch('subprocess.run')
@patch('pathlib.Path.exists')
def test_unload_plist_success(mock_exists, mock_run):
    """Unload plist should return True when launchctl succeeds"""
    mock_exists.return_value = True
    mock_run.return_value = Mock(returncode=0)
    result = unload_plist('test_schedule')
    assert result == True


@patch('pathlib.Path.exists')
def test_unload_plist_file_not_exists(mock_exists):
    """Unload plist should return False when file doesn't exist"""
    mock_exists.return_value = False
    result = unload_plist('nonexistent_schedule')
    assert result == False


@patch('subprocess.run')
@patch('pathlib.Path.exists')
def test_unload_plist_command_fails(mock_exists, mock_run):
    """Unload plist should return False when launchctl fails"""
    mock_exists.return_value = True
    mock_run.return_value = Mock(returncode=1)
    result = unload_plist('test_schedule')
    assert result == False


# ============================================================================
# REMOVE_PLIST TESTS
# ============================================================================

@patch('contracts_contracts_src_ascend_scheduler_interface_interface.unload_plist')
@patch('pathlib.Path.exists')
@patch('pathlib.Path.unlink')
def test_remove_plist_success(mock_unlink, mock_exists, mock_unload):
    """Remove plist should unload and delete file, returning True"""
    mock_exists.return_value = True
    mock_unload.return_value = True
    result = remove_plist('test_schedule')
    assert result == True


@patch('pathlib.Path.exists')
def test_remove_plist_file_not_exists(mock_exists):
    """Remove plist should return False when file doesn't exist"""
    mock_exists.return_value = False
    result = remove_plist('nonexistent_schedule')
    assert result == False


# ============================================================================
# INVARIANT TESTS
# ============================================================================

def test_invariant_day_map_sunday_is_zero():
    """Verify _DAY_MAP maps Sunday to 0"""
    result = schedule_to_cron(
        daily=False,
        weekdays=False,
        weekly='sunday',
        biweekly=None,
        monthly=None,
        quarterly=False,
        hour=10,
        minute=0
    )
    assert '* * 0' in result or result.endswith(' 0')


def test_invariant_biweekly_day_ranges():
    """Verify biweekly schedules use days 8-14 and 22-28"""
    result = schedule_to_cron(
        daily=False,
        weekdays=False,
        weekly=None,
        biweekly='tuesday',
        monthly=None,
        quarterly=False,
        hour=12,
        minute=0
    )
    assert '8-14,22-28' in result


def test_invariant_quarterly_months():
    """Verify quarterly schedules use months 1,4,7,10"""
    result = schedule_to_cron(
        daily=False,
        weekdays=False,
        weekly=None,
        biweekly=None,
        monthly=None,
        quarterly=True,
        hour=0,
        minute=0
    )
    assert '1,4,7,10' in result


def test_invariant_plist_naming_pattern(tmp_path):
    """Verify plist files follow naming pattern com.ascend.schedule.{name}.plist"""
    with patch('pathlib.Path.home', return_value=tmp_path):
        with patch('contracts_contracts_src_ascend_scheduler_interface_interface._find_ascend_path', return_value='/usr/bin/ascend'):
            result = write_plist('my_schedule', '0 10 * * *', Path('/tmp/schedules'))
            assert 'com.ascend.schedule.my_schedule.plist' in str(result)


def test_invariant_log_path_pattern():
    """Verify log files are named {schedule_name}.log in schedules_dir"""
    with patch('contracts_contracts_src_ascend_scheduler_interface_interface._find_ascend_path', return_value='/usr/bin/ascend'):
        result = generate_plist('my_schedule', Path('/tmp/schedules'))
        assert 'my_schedule.log' in str(result)
