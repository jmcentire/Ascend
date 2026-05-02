"""
Contract tests for contracts_contracts_src_ascend_audit_interface_interface

This test suite verifies the audit interface implementation against its contract.
Tests cover happy paths, edge cases, error cases, and invariants using a three-tier
approach: unit tests with mocking, integration tests with real I/O, and comprehensive
edge case coverage.
"""

import pytest
import json
import tempfile
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch, mock_open, MagicMock
from datetime import datetime, timezone
from typing import Any, Optional
import time


# Import the module under test
# Adjust import based on actual module structure
try:
    from contracts.contracts_src_ascend_audit_interface.interface import (
        _audit_path,
        log_operation,
        read_audit,
    )
except ImportError:
    # Fallback for different module structures
    import contracts_contracts_src_ascend_audit_interface_interface as audit_module
    _audit_path = audit_module._audit_path
    log_operation = audit_module.log_operation
    read_audit = audit_module.read_audit


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def temp_audit_dir(tmp_path):
    """Provides a temporary directory for audit logs."""
    audit_dir = tmp_path / "audit_test"
    audit_dir.mkdir(exist_ok=True)
    return audit_dir


@pytest.fixture
def mock_history_dir(temp_audit_dir, monkeypatch):
    """Mocks the HISTORY_DIR constant in ascend.config."""
    # Mock the config module
    mock_config = Mock()
    mock_config.HISTORY_DIR = temp_audit_dir
    
    # Patch where it's used
    monkeypatch.setattr('contracts_contracts_src_ascend_audit_interface_interface.HISTORY_DIR', 
                        temp_audit_dir, raising=False)
    
    return temp_audit_dir


@pytest.fixture
def prepopulated_audit_log(temp_audit_dir):
    """Creates a pre-populated audit log file with sample entries."""
    audit_file = temp_audit_dir / "audit.jsonl"
    entries = [
        {
            "timestamp": "2024-01-01T10:00:00.000000Z",
            "command": "cmd1",
            "args": {"key": "value1"},
            "result": "success",
            "error": None
        },
        {
            "timestamp": "2024-01-01T11:00:00.000000Z",
            "command": "cmd2",
            "args": {"key": "value2"},
            "result": "success",
            "error": None
        },
        {
            "timestamp": "2024-01-01T12:00:00.000000Z",
            "command": "cmd3",
            "args": {},
            "result": None,
            "error": "some_error"
        },
    ]
    
    with open(audit_file, 'w') as f:
        for entry in entries:
            f.write(json.dumps(entry) + '\n')
    
    return audit_file


@pytest.fixture
def mock_datetime():
    """Provides a mock datetime for deterministic timestamps."""
    with patch('contracts_contracts_src_ascend_audit_interface_interface.datetime') as mock_dt:
        fixed_time = datetime(2024, 1, 15, 12, 30, 45, 123456, tzinfo=timezone.utc)
        mock_dt.now.return_value = fixed_time
        mock_dt.timezone = timezone
        yield mock_dt


# ============================================================================
# HAPPY PATH TESTS
# ============================================================================

def test_audit_path_returns_path_object(mock_history_dir):
    """Happy path: _audit_path returns Path object for audit.jsonl"""
    result = _audit_path()
    
    # Assertions
    assert isinstance(result, Path), "Result is a Path object"
    assert result.name == "audit.jsonl", "Path ends with 'audit.jsonl'"
    assert result.parent == mock_history_dir, "Parent is HISTORY_DIR"


def test_log_operation_basic(mock_history_dir, mock_datetime):
    """Happy path: log_operation appends entry with all fields"""
    command = "test_command"
    args = {"key": "value"}
    result = "success"
    error = ""
    
    log_operation(command, args, result, error)
    
    audit_file = mock_history_dir / "audit.jsonl"
    
    # Assertions
    assert audit_file.exists(), "File exists after write"
    
    with open(audit_file, 'r') as f:
        lines = f.readlines()
        assert len(lines) == 1, "One entry written"
        
        entry = json.loads(lines[0])
        assert "timestamp" in entry, "Entry contains timestamp"
        assert entry["command"] == command, "Entry contains command"
        assert entry["args"] == args, "Entry contains args"
        assert entry["result"] == result, "Entry contains result"
        assert entry["error"] == error, "Entry contains error"
        
        # Verify UTC ISO format timestamp
        try:
            datetime.fromisoformat(entry["timestamp"].replace('Z', '+00:00'))
        except ValueError:
            pytest.fail("Timestamp not in valid ISO format")


def test_log_operation_minimal(mock_history_dir):
    """Happy path: log_operation with only required command field"""
    command = "minimal_command"
    
    log_operation(command, None, None, None)
    
    audit_file = mock_history_dir / "audit.jsonl"
    
    # Assertions
    assert audit_file.exists(), "File exists"
    
    with open(audit_file, 'r') as f:
        entry = json.loads(f.readline())
        assert entry["command"] == command, "Entry contains command"
        assert entry["args"] is None or entry["args"] == {}, "Optional args is None or empty"
        assert entry["result"] is None or entry["result"] == "", "Optional result is None or empty"
        assert entry["error"] is None or entry["error"] == "", "Optional error is None or empty"


def test_log_operation_creates_parent_directory(tmp_path):
    """Happy path: log_operation creates parent directory if it doesn't exist"""
    new_dir = tmp_path / "new_history"
    
    with patch('contracts_contracts_src_ascend_audit_interface_interface.HISTORY_DIR', new_dir):
        assert not new_dir.exists(), "Directory doesn't exist initially"
        
        log_operation("create_dir_test", None, None, None)
        
        # Assertions
        assert new_dir.exists(), "Parent directory exists after call"
        assert (new_dir / "audit.jsonl").exists(), "File is created"


def test_log_operation_appends_multiple(mock_history_dir):
    """Happy path: log_operation appends multiple entries maintaining order"""
    commands = ["cmd1", "cmd2", "cmd3"]
    
    for cmd in commands:
        log_operation(cmd, None, None, None)
        time.sleep(0.001)  # Small delay to ensure different timestamps
    
    audit_file = mock_history_dir / "audit.jsonl"
    
    with open(audit_file, 'r') as f:
        lines = f.readlines()
        
    # Assertions
    assert len(lines) == len(commands), "Multiple entries exist"
    
    entries = [json.loads(line) for line in lines]
    
    # Check chronological order
    timestamps = [datetime.fromisoformat(e["timestamp"].replace('Z', '+00:00')) for e in entries]
    assert timestamps == sorted(timestamps), "Entries are in chronological order"
    
    # Check commands match
    assert [e["command"] for e in entries] == commands, "Commands in correct order"


def test_read_audit_basic(prepopulated_audit_log, mock_history_dir):
    """Happy path: read_audit returns last N entries"""
    with patch('contracts_contracts_src_ascend_audit_interface_interface.HISTORY_DIR', mock_history_dir):
        result = read_audit(5)
    
    # Assertions
    assert isinstance(result, list), "Returns list"
    assert len(result) <= 5, "Length is at most last_n"
    assert all(isinstance(entry, dict) for entry in result), "Entries are dictionaries"
    
    # Check chronological order
    if len(result) > 1:
        timestamps = [e.get("timestamp", "") for e in result]
        assert timestamps == sorted(timestamps), "Entries in chronological order"


def test_read_audit_nonexistent_file(mock_history_dir):
    """Happy path: read_audit returns empty list if file doesn't exist"""
    with patch('contracts_contracts_src_ascend_audit_interface_interface.HISTORY_DIR', mock_history_dir):
        result = read_audit(10)
    
    # Assertions
    assert result == [], "Returns empty list"


def test_read_audit_skips_blank_lines(temp_audit_dir, mock_history_dir):
    """Happy path: read_audit skips blank lines in file"""
    audit_file = temp_audit_dir / "audit.jsonl"
    
    # Create file with blank lines
    with open(audit_file, 'w') as f:
        f.write(json.dumps({"timestamp": "2024-01-01T10:00:00Z", "command": "cmd1", "args": {}, "result": None, "error": None}) + '\n')
        f.write('\n')  # Blank line
        f.write('   \n')  # Whitespace only
        f.write(json.dumps({"timestamp": "2024-01-01T11:00:00Z", "command": "cmd2", "args": {}, "result": None, "error": None}) + '\n')
        f.write('\n')  # Another blank
    
    with patch('contracts_contracts_src_ascend_audit_interface_interface.HISTORY_DIR', mock_history_dir):
        result = read_audit(10)
    
    # Assertions
    assert len(result) == 2, "Only valid entries returned"
    assert all(e["command"] in ["cmd1", "cmd2"] for e in result), "Blank lines are skipped"


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

def test_read_audit_zero(mock_history_dir, prepopulated_audit_log):
    """Edge case: read_audit with last_n=0"""
    with patch('contracts_contracts_src_ascend_audit_interface_interface.HISTORY_DIR', mock_history_dir):
        result = read_audit(0)
    
    # Assertions
    assert result == [], "Returns empty list"


def test_read_audit_one(mock_history_dir, prepopulated_audit_log):
    """Edge case: read_audit with last_n=1"""
    with patch('contracts_contracts_src_ascend_audit_interface_interface.HISTORY_DIR', mock_history_dir):
        result = read_audit(1)
    
    # Assertions
    assert len(result) == 1, "Returns list with exactly 1 entry"
    assert result[0]["command"] == "cmd3", "Entry is the most recent"


def test_read_audit_more_than_total(temp_audit_dir, mock_history_dir):
    """Edge case: read_audit with last_n greater than total entries"""
    audit_file = temp_audit_dir / "audit.jsonl"
    
    # Create file with only 5 entries
    with open(audit_file, 'w') as f:
        for i in range(5):
            entry = {"timestamp": f"2024-01-01T{i:02d}:00:00Z", "command": f"cmd{i}", "args": {}, "result": None, "error": None}
            f.write(json.dumps(entry) + '\n')
    
    with patch('contracts_contracts_src_ascend_audit_interface_interface.HISTORY_DIR', mock_history_dir):
        result = read_audit(1000)
    
    # Assertions
    assert len(result) == 5, "Returns all available entries"


def test_read_audit_negative(mock_history_dir, prepopulated_audit_log):
    """Edge case: read_audit with negative last_n"""
    with patch('contracts_contracts_src_ascend_audit_interface_interface.HISTORY_DIR', mock_history_dir):
        result = read_audit(-5)
    
    # Assertions
    assert isinstance(result, list), "Returns a list"


def test_read_audit_empty_file(temp_audit_dir, mock_history_dir):
    """Edge case: read_audit on empty file"""
    audit_file = temp_audit_dir / "audit.jsonl"
    audit_file.touch()  # Create empty file
    
    with patch('contracts_contracts_src_ascend_audit_interface_interface.HISTORY_DIR', mock_history_dir):
        result = read_audit(10)
    
    # Assertions
    assert result == [], "Returns empty list"


def test_log_operation_unicode_content(mock_history_dir):
    """Edge case: log_operation with unicode characters"""
    command = "unicode_test_🎉"
    args = {"emoji": "🚀", "chinese": "你好"}
    result = "成功"
    
    log_operation(command, args, result, None)
    
    audit_file = mock_history_dir / "audit.jsonl"
    
    # Assertions
    assert audit_file.exists(), "Entry is written"
    
    with open(audit_file, 'r', encoding='utf-8') as f:
        entry = json.loads(f.readline())
        assert entry["command"] == command, "Unicode command preserved"
        assert entry["args"] == args, "Unicode args preserved"
        assert entry["result"] == result, "Unicode result preserved"


def test_log_operation_special_characters(mock_history_dir):
    """Edge case: log_operation with special JSON characters"""
    command = 'special\\"chars\\n\\t'
    args = {"quote": '"', "newline": "\n", "tab": "\t"}
    
    log_operation(command, args, None, None)
    
    audit_file = mock_history_dir / "audit.jsonl"
    
    # Assertions
    assert audit_file.exists(), "Entry is written"
    
    with open(audit_file, 'r') as f:
        entry = json.loads(f.readline())
        # Special characters should be properly handled by JSON
        assert "command" in entry, "Entry contains command field"


def test_log_operation_nested_structures(mock_history_dir):
    """Edge case: log_operation with deeply nested dict in args"""
    command = "nested"
    args = {"level1": {"level2": {"level3": "deep"}}}
    
    log_operation(command, args, None, None)
    
    audit_file = mock_history_dir / "audit.jsonl"
    
    # Assertions
    assert audit_file.exists(), "Entry is written"
    
    with open(audit_file, 'r') as f:
        entry = json.loads(f.readline())
        assert entry["args"] == args, "Nested structure is preserved"


def test_log_operation_large_payload(mock_history_dir):
    """Edge case: log_operation with large args dictionary"""
    command = "large_payload"
    args = {f"key_{i}": f"value_{i}" for i in range(1000)}
    
    log_operation(command, args, None, None)
    
    audit_file = mock_history_dir / "audit.jsonl"
    
    # Assertions
    assert audit_file.exists(), "Entry is written"
    
    with open(audit_file, 'r') as f:
        entry = json.loads(f.readline())
        assert len(entry["args"]) == 1000, "Large payload preserved"


def test_concurrent_writes(mock_history_dir):
    """Edge case: Multiple concurrent log_operation calls"""
    # Simulate sequential writes (true concurrency hard to test in pytest)
    commands = [f"concurrent_{i}" for i in range(10)]
    
    for cmd in commands:
        log_operation(cmd, None, None, None)
    
    audit_file = mock_history_dir / "audit.jsonl"
    
    with open(audit_file, 'r') as f:
        lines = f.readlines()
    
    # Assertions
    assert len(lines) == 10, "All entries are present"
    
    # Check no corruption
    for line in lines:
        try:
            entry = json.loads(line)
            assert "command" in entry, "Entry has command field"
        except json.JSONDecodeError:
            pytest.fail("Corrupted entry found")


def test_large_file_performance(temp_audit_dir, mock_history_dir):
    """Edge case: read_audit on file with 1000+ entries"""
    audit_file = temp_audit_dir / "audit.jsonl"
    
    # Create file with 1000 entries
    with open(audit_file, 'w') as f:
        for i in range(1000):
            entry = {
                "timestamp": f"2024-01-01T{i % 24:02d}:{i % 60:02d}:{i % 60:02d}Z",
                "command": f"cmd{i}",
                "args": {"index": i},
                "result": None,
                "error": None
            }
            f.write(json.dumps(entry) + '\n')
    
    with patch('contracts_contracts_src_ascend_audit_interface_interface.HISTORY_DIR', mock_history_dir):
        result = read_audit(10)
    
    # Assertions
    assert len(result) == 10, "Returns exactly 10 entries"
    
    # Verify we got the last 10
    assert result[-1]["args"]["index"] == 999, "Returns last entries"


# ============================================================================
# ERROR CASE TESTS
# ============================================================================

def test_log_operation_file_write_error(mock_history_dir):
    """Error case: log_operation fails when file cannot be opened for writing"""
    audit_file = mock_history_dir / "audit.jsonl"
    audit_file.touch()
    
    # Make file read-only
    os.chmod(audit_file, 0o444)
    
    try:
        # Expect some exception when writing fails
        with pytest.raises(Exception):  # Could be PermissionError, OSError, etc.
            log_operation("write_fail", None, None, None)
    finally:
        # Restore permissions for cleanup
        os.chmod(audit_file, 0o644)


def test_log_operation_directory_creation_error():
    """Error case: log_operation fails when parent directory cannot be created"""
    # Mock Path.mkdir to raise PermissionError
    with patch('contracts_contracts_src_ascend_audit_interface_interface.HISTORY_DIR', Path('/root/forbidden_dir')):
        with patch.object(Path, 'mkdir', side_effect=PermissionError("Cannot create directory")):
            with pytest.raises(Exception):  # PermissionError or similar
                log_operation("dir_fail", None, None, None)


def test_log_operation_serialization_error(mock_history_dir):
    """Error case: log_operation fails when JSON serialization fails"""
    # This is tricky since contract mentions default=str fallback
    # We'd need to mock json.dumps to force failure
    with patch('contracts_contracts_src_ascend_audit_interface_interface.json.dumps', side_effect=TypeError("Not serializable")):
        with pytest.raises(Exception):  # TypeError or custom serialization error
            log_operation("serialize_fail", {"key": "value"}, None, None)


def test_read_audit_file_read_error(temp_audit_dir, mock_history_dir):
    """Error case: read_audit fails when file exists but cannot be read"""
    audit_file = temp_audit_dir / "audit.jsonl"
    audit_file.write_text('{"test": "data"}\n')
    
    # Make file write-only (no read permission)
    os.chmod(audit_file, 0o222)
    
    try:
        with patch('contracts_contracts_src_ascend_audit_interface_interface.HISTORY_DIR', mock_history_dir):
            with pytest.raises(Exception):  # PermissionError or similar
                read_audit(10)
    finally:
        # Restore permissions for cleanup
        os.chmod(audit_file, 0o644)


def test_read_audit_json_parse_error(temp_audit_dir, mock_history_dir):
    """Error case: read_audit fails when file contains invalid JSON"""
    audit_file = temp_audit_dir / "audit.jsonl"
    
    # Write malformed JSON
    with open(audit_file, 'w') as f:
        f.write('{"valid": "json"}\n')
        f.write('{invalid json here\n')
        f.write('{"another": "valid"}\n')
    
    with patch('contracts_contracts_src_ascend_audit_interface_interface.HISTORY_DIR', mock_history_dir):
        with pytest.raises(Exception):  # json.JSONDecodeError or similar
            read_audit(10)


# ============================================================================
# INVARIANT TESTS
# ============================================================================

def test_invariant_append_only(mock_history_dir):
    """Invariant: Audit log is append-only, no modifications"""
    # Write initial entries
    log_operation("initial1", None, None, None)
    log_operation("initial2", None, None, None)
    
    audit_file = mock_history_dir / "audit.jsonl"
    
    # Read initial content
    with open(audit_file, 'r') as f:
        initial_content = f.read()
    
    # Write more entries
    log_operation("new1", None, None, None)
    log_operation("new2", None, None, None)
    
    # Read new content
    with open(audit_file, 'r') as f:
        new_content = f.read()
    
    # Assertions
    assert new_content.startswith(initial_content), "Original entries are preserved"
    assert len(new_content) > len(initial_content), "New entries are appended"


def test_invariant_single_line_json(mock_history_dir):
    """Invariant: Each entry is a single line of JSON followed by newline"""
    log_operation("line_test", {"key": "value\nwith\nnewlines"}, None, None)
    
    audit_file = mock_history_dir / "audit.jsonl"
    
    with open(audit_file, 'r') as f:
        content = f.read()
        lines = content.split('\n')
    
    # Assertions
    # Should have one line of content plus empty string after final newline
    assert len([line for line in lines if line]) == 1, "Entry is single line"
    assert content.endswith('\n'), "Entry ends with newline"
    
    # Parse the line to ensure it's valid JSON
    valid_line = [line for line in lines if line][0]
    entry = json.loads(valid_line)
    assert isinstance(entry, dict), "Line is valid JSON object"


def test_invariant_utc_timestamps(mock_history_dir):
    """Invariant: All timestamps are in UTC ISO format"""
    log_operation("timestamp_test", None, None, None)
    
    audit_file = mock_history_dir / "audit.jsonl"
    
    with open(audit_file, 'r') as f:
        entry = json.loads(f.readline())
    
    # Assertions
    timestamp_str = entry["timestamp"]
    
    # Parse as ISO format
    try:
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        # Check it's UTC
        assert dt.tzinfo is not None, "Timestamp includes timezone info"
    except ValueError:
        pytest.fail("Timestamp is not in valid ISO format")


def test_invariant_file_path(mock_history_dir):
    """Invariant: File path is always HISTORY_DIR/audit.jsonl"""
    with patch('contracts_contracts_src_ascend_audit_interface_interface.HISTORY_DIR', mock_history_dir):
        path = _audit_path()
    
    # Assertions
    assert path.name == "audit.jsonl", "Path ends with audit.jsonl"
    assert path.parent == mock_history_dir, "Parent is HISTORY_DIR"


def test_invariant_chronological_order(mock_history_dir):
    """Invariant: Entries maintain chronological order with newest at end"""
    # Write multiple entries with small delays
    commands = ["cmd1", "cmd2", "cmd3", "cmd4"]
    
    for cmd in commands:
        log_operation(cmd, None, None, None)
        time.sleep(0.001)  # Small delay to ensure different timestamps
    
    audit_file = mock_history_dir / "audit.jsonl"
    
    with open(audit_file, 'r') as f:
        entries = [json.loads(line) for line in f]
    
    # Assertions
    timestamps = [datetime.fromisoformat(e["timestamp"].replace('Z', '+00:00')) for e in entries]
    
    # Check monotonically increasing (or equal for very fast writes)
    for i in range(len(timestamps) - 1):
        assert timestamps[i] <= timestamps[i + 1], "Timestamps are monotonically increasing"
    
    # Newest is at end
    assert timestamps[-1] >= timestamps[0], "Newest entry is at end"


# ============================================================================
# ADDITIONAL INTEGRATION TESTS
# ============================================================================

def test_full_workflow_integration(mock_history_dir):
    """Integration test: Complete workflow of logging and reading"""
    # Log several operations
    log_operation("start", {"user": "alice"}, "initialized", None)
    log_operation("process", {"items": 100}, "completed", None)
    log_operation("error_case", None, None, "Something went wrong")
    log_operation("finish", {"status": "done"}, "success", None)
    
    # Read all entries
    with patch('contracts_contracts_src_ascend_audit_interface_interface.HISTORY_DIR', mock_history_dir):
        entries = read_audit(100)
    
    # Assertions
    assert len(entries) == 4, "All entries retrieved"
    assert entries[0]["command"] == "start", "First entry correct"
    assert entries[-1]["command"] == "finish", "Last entry correct"
    assert entries[2]["error"] == "Something went wrong", "Error field preserved"


def test_read_write_consistency(mock_history_dir):
    """Integration test: What is written can be read back correctly"""
    test_data = {
        "command": "test_cmd",
        "args": {"complex": {"nested": [1, 2, 3]}, "unicode": "测试"},
        "result": "success",
        "error": None
    }
    
    log_operation(
        test_data["command"],
        test_data["args"],
        test_data["result"],
        test_data["error"]
    )
    
    with patch('contracts_contracts_src_ascend_audit_interface_interface.HISTORY_DIR', mock_history_dir):
        entries = read_audit(1)
    
    # Assertions
    assert len(entries) == 1, "One entry retrieved"
    entry = entries[0]
    
    assert entry["command"] == test_data["command"], "Command matches"
    assert entry["args"] == test_data["args"], "Args match exactly"
    assert entry["result"] == test_data["result"], "Result matches"
    assert entry["error"] == test_data["error"], "Error matches"
