"""
Executable pytest test suite for audit_interface contract.

Tests cover:
- Unit tests for _audit_path, log_operation, read_audit
- Integration tests for write-read workflows
- Edge cases: empty files, boundary values, empty optional fields
- Error cases: permission errors, malformed JSON, non-serializable objects
- Invariant tests: append-only, JSONL format, UTC timestamps, consistent path

Uses pytest fixtures for temporary directories and sample data.
Mocks filesystem errors to test error handling paths.
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock
from datetime import datetime, timezone
import os

# Import the component under test
from contracts.src_ascend_audit.interface import (
    _audit_path,
    log_operation,
    read_audit
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_history_dir(tmp_path, monkeypatch):
    """Create a temporary HISTORY_DIR for testing."""
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    
    # Mock the config module to return our temp directory
    mock_config = MagicMock()
    mock_config.HISTORY_DIR = history_dir
    monkeypatch.setattr("contracts_src_ascend_audit_interface.config", mock_config)
    
    return history_dir


@pytest.fixture
def audit_file(temp_history_dir):
    """Return the path to the audit file."""
    return temp_history_dir / "audit.jsonl"


@pytest.fixture
def populated_audit_file(audit_file):
    """Create an audit file with 10 sample entries."""
    entries = []
    for i in range(10):
        entry = {
            "timestamp": f"2024-01-{i+1:02d}T10:00:00+00:00",
            "command": f"command_{i}",
        }
        if i % 2 == 0:
            entry["args"] = {"index": i}
        if i % 3 == 0:
            entry["result"] = f"result_{i}"
        entries.append(entry)
    
    with open(audit_file, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    
    return audit_file, entries


# ============================================================================
# Unit Tests: _audit_path
# ============================================================================

def test_audit_path_returns_correct_path(temp_history_dir):
    """Happy path: _audit_path returns Path object pointing to HISTORY_DIR/audit.jsonl"""
    result = _audit_path()
    
    assert isinstance(result, Path)
    assert result.name == "audit.jsonl"
    assert result.parent == temp_history_dir


def test_audit_file_path_invariant(temp_history_dir):
    """Invariant: Audit file path is always HISTORY_DIR/audit.jsonl"""
    result1 = _audit_path()
    result2 = _audit_path()
    
    assert result1 == result2
    assert result1.name == "audit.jsonl"
    assert result1.parent == temp_history_dir


# ============================================================================
# Unit Tests: log_operation - Happy Path
# ============================================================================

def test_log_operation_minimal_fields(temp_history_dir, audit_file):
    """Happy path: log_operation with only command creates valid entry"""
    log_operation("test_command", None, None, None)
    
    assert audit_file.exists()
    
    with open(audit_file, "r") as f:
        lines = f.readlines()
    
    assert len(lines) == 1
    entry = json.loads(lines[0])
    
    assert "timestamp" in entry
    assert entry["command"] == "test_command"
    assert "args" not in entry or entry.get("args") is None
    assert "result" not in entry or entry.get("result") is None
    assert "error" not in entry or entry.get("error") is None
    
    # Verify timestamp is ISO8601
    datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))


def test_log_operation_all_fields(temp_history_dir, audit_file):
    """Happy path: log_operation with all fields creates complete entry"""
    args_dict = {"key": "value", "number": 42}
    log_operation("execute", args_dict, "success", None)
    
    with open(audit_file, "r") as f:
        entry = json.loads(f.readline())
    
    assert entry["command"] == "execute"
    assert entry["args"] == args_dict
    assert entry["result"] == "success"
    assert "timestamp" in entry
    
    # Verify timestamp is UTC
    ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
    assert ts.tzinfo is not None


def test_log_operation_with_error_field(temp_history_dir, audit_file):
    """Happy path: log_operation with error field logs error information"""
    log_operation("failed_operation", None, None, "Permission denied")
    
    with open(audit_file, "r") as f:
        entry = json.loads(f.readline())
    
    assert entry["command"] == "failed_operation"
    assert entry["error"] == "Permission denied"


# ============================================================================
# Unit Tests: log_operation - Edge Cases
# ============================================================================

def test_log_operation_creates_parent_directories(tmp_path, monkeypatch):
    """Edge case: log_operation creates parent directories if they don't exist"""
    # Create a non-existent directory path
    history_dir = tmp_path / "nested" / "deep" / "history"
    
    mock_config = MagicMock()
    mock_config.HISTORY_DIR = history_dir
    monkeypatch.setattr("contracts_src_ascend_audit_interface.config", mock_config)
    
    assert not history_dir.exists()
    
    log_operation("test", None, None, None)
    
    audit_file = history_dir / "audit.jsonl"
    assert audit_file.exists()
    assert audit_file.parent.exists()


def test_log_operation_empty_optional_fields(temp_history_dir, audit_file):
    """Edge case: log_operation with empty strings for optional fields excludes them"""
    log_operation("test", None, "", "")
    
    with open(audit_file, "r") as f:
        entry = json.loads(f.readline())
    
    # Empty strings should be treated as falsy and excluded
    assert entry["command"] == "test"
    # Check that empty fields are not in entry or are None/empty
    assert not entry.get("result")
    assert not entry.get("error")


def test_log_operation_non_serializable_objects(temp_history_dir, audit_file):
    """Error case: log_operation handles non-serializable objects with default=str"""
    # Create a non-serializable object
    class CustomObject:
        def __str__(self):
            return "CustomObject"
    
    args_with_object = {"obj": CustomObject(), "normal": "value"}
    
    # Should not raise exception due to default=str in json.dumps
    log_operation("test", args_with_object, None, None)
    
    assert audit_file.exists()
    with open(audit_file, "r") as f:
        entry = json.loads(f.readline())
    
    assert entry["command"] == "test"
    # The object should be serialized as string
    assert "args" in entry


# ============================================================================
# Unit Tests: log_operation - Error Cases
# ============================================================================

def test_log_operation_permission_denied(temp_history_dir, monkeypatch):
    """Error case: log_operation raises file_write_error when permissions denied"""
    # Mock the open function to raise PermissionError
    original_open = open
    
    def mock_open_func(file, mode='r', *args, **kwargs):
        if 'audit.jsonl' in str(file) and 'a' in mode:
            raise PermissionError("Permission denied")
        return original_open(file, mode, *args, **kwargs)
    
    monkeypatch.setattr("builtins.open", mock_open_func)
    
    # Should raise an exception or handle gracefully
    with pytest.raises((PermissionError, OSError)):
        log_operation("test", None, None, None)


# ============================================================================
# Unit Tests: read_audit - Happy Path
# ============================================================================

def test_read_audit_last_n_entries(populated_audit_file):
    """Happy path: read_audit returns last N entries in chronological order"""
    audit_file, all_entries = populated_audit_file
    
    result = read_audit(3)
    
    assert len(result) == 3
    # Should return the last 3 entries (index 7, 8, 9)
    assert result[0]["command"] == "command_7"
    assert result[1]["command"] == "command_8"
    assert result[2]["command"] == "command_9"
    
    # Verify chronological order (oldest to newest of last 3)
    timestamps = [r["timestamp"] for r in result]
    assert timestamps == sorted(timestamps)


def test_read_audit_chronological_order(temp_history_dir, audit_file):
    """Happy path: read_audit returns entries in chronological order (oldest to newest of last_n)"""
    # Create entries with distinct timestamps
    entries = [
        {"timestamp": "2024-01-01T10:00:00+00:00", "command": "first"},
        {"timestamp": "2024-01-02T10:00:00+00:00", "command": "second"},
        {"timestamp": "2024-01-03T10:00:00+00:00", "command": "third"},
        {"timestamp": "2024-01-04T10:00:00+00:00", "command": "fourth"},
        {"timestamp": "2024-01-05T10:00:00+00:00", "command": "fifth"},
    ]
    
    with open(audit_file, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    
    result = read_audit(3)
    
    assert len(result) == 3
    # Last 3 entries in chronological order
    assert result[0]["command"] == "third"
    assert result[1]["command"] == "fourth"
    assert result[2]["command"] == "fifth"
    
    # Verify timestamps are in ascending order
    ts0 = datetime.fromisoformat(result[0]["timestamp"].replace("Z", "+00:00"))
    ts1 = datetime.fromisoformat(result[1]["timestamp"].replace("Z", "+00:00"))
    ts2 = datetime.fromisoformat(result[2]["timestamp"].replace("Z", "+00:00"))
    assert ts0 < ts1 < ts2


# ============================================================================
# Unit Tests: read_audit - Edge Cases
# ============================================================================

def test_read_audit_empty_file(temp_history_dir):
    """Edge case: read_audit returns empty list when audit file doesn't exist"""
    result = read_audit(50)
    
    assert result == []
    assert isinstance(result, list)


def test_read_audit_last_n_greater_than_total(populated_audit_file):
    """Edge case: read_audit returns all entries when last_n exceeds total"""
    audit_file, all_entries = populated_audit_file
    
    result = read_audit(100)
    
    assert len(result) == len(all_entries)
    assert result[0]["command"] == "command_0"
    assert result[-1]["command"] == "command_9"


def test_read_audit_last_n_zero(populated_audit_file):
    """Edge case: read_audit with last_n=0 returns empty list"""
    result = read_audit(0)
    
    assert result == []


def test_read_audit_skips_empty_lines(temp_history_dir, audit_file):
    """Edge case: read_audit skips empty lines in file"""
    entries = [
        {"timestamp": "2024-01-01T10:00:00+00:00", "command": "first"},
        {"timestamp": "2024-01-02T10:00:00+00:00", "command": "second"},
        {"timestamp": "2024-01-03T10:00:00+00:00", "command": "third"},
    ]
    
    with open(audit_file, "w") as f:
        f.write(json.dumps(entries[0]) + "\n")
        f.write("\n")  # Empty line
        f.write(json.dumps(entries[1]) + "\n")
        f.write("\n")  # Empty line
        f.write(json.dumps(entries[2]) + "\n")
    
    result = read_audit(10)
    
    assert len(result) == 3
    assert result[0]["command"] == "first"
    assert result[1]["command"] == "second"
    assert result[2]["command"] == "third"


# ============================================================================
# Unit Tests: read_audit - Error Cases
# ============================================================================

def test_read_audit_malformed_json(temp_history_dir, audit_file):
    """Error case: read_audit raises json_decode_error for malformed JSON"""
    with open(audit_file, "w") as f:
        f.write('{"timestamp": "2024-01-01T10:00:00+00:00", "command": "valid"}\n')
        f.write('{"invalid json without closing brace"\n')
        f.write('{"timestamp": "2024-01-03T10:00:00+00:00", "command": "also_valid"}\n')
    
    with pytest.raises(json.JSONDecodeError):
        read_audit(10)


def test_read_audit_permission_denied(temp_history_dir, audit_file, monkeypatch):
    """Error case: read_audit raises file_read_error when permissions denied"""
    # Create the file first
    with open(audit_file, "w") as f:
        f.write('{"timestamp": "2024-01-01T10:00:00+00:00", "command": "test"}\n')
    
    # Mock open to raise PermissionError when reading audit file
    original_open = open
    
    def mock_open_func(file, mode='r', *args, **kwargs):
        if 'audit.jsonl' in str(file) and 'r' in mode:
            raise PermissionError("Permission denied")
        return original_open(file, mode, *args, **kwargs)
    
    monkeypatch.setattr("builtins.open", mock_open_func)
    
    with pytest.raises(PermissionError):
        read_audit(10)


# ============================================================================
# Invariant Tests
# ============================================================================

def test_audit_append_only_invariant(temp_history_dir, audit_file):
    """Invariant: Audit log is append-only, entries are never modified"""
    # Write first entry
    log_operation("first", None, None, None)
    
    with open(audit_file, "r") as f:
        first_content = f.read()
    
    # Write second entry
    log_operation("second", None, None, None)
    
    with open(audit_file, "r") as f:
        second_content = f.read()
    
    # First content should be prefix of second content
    assert second_content.startswith(first_content)
    
    # Count entries
    entries = read_audit(100)
    assert len(entries) == 2
    assert entries[0]["command"] == "first"
    assert entries[1]["command"] == "second"


def test_jsonl_format_invariant(temp_history_dir, audit_file):
    """Invariant: Each audit entry is a single JSON line"""
    log_operation("cmd1", {"key": "value"}, None, None)
    log_operation("cmd2", None, "result", None)
    log_operation("cmd3", None, None, "error")
    
    with open(audit_file, "r") as f:
        lines = f.readlines()
    
    assert len(lines) == 3
    
    for line in lines:
        # Each line should be valid JSON
        entry = json.loads(line.strip())
        assert isinstance(entry, dict)
        assert "timestamp" in entry
        assert "command" in entry


def test_timestamp_utc_iso8601_invariant(temp_history_dir, audit_file):
    """Invariant: All timestamps are UTC and ISO8601 format"""
    log_operation("test1", None, None, None)
    log_operation("test2", None, None, None)
    log_operation("test3", None, None, None)
    
    entries = read_audit(10)
    
    for entry in entries:
        timestamp_str = entry["timestamp"]
        
        # Should be parseable as ISO8601
        ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        
        # Should be UTC (either has +00:00 or Z suffix)
        assert (timestamp_str.endswith("+00:00") or 
                timestamp_str.endswith("Z") or
                ts.tzinfo == timezone.utc or
                "+00:00" in timestamp_str)


# ============================================================================
# Integration Tests
# ============================================================================

def test_integration_write_read_workflow(temp_history_dir, audit_file):
    """Integration: Write multiple entries and read them back correctly"""
    # Write various entries
    log_operation("init", None, "initialized", None)
    log_operation("execute", {"param": "value"}, "success", None)
    log_operation("cleanup", None, None, None)
    log_operation("error_op", {"x": 1}, None, "failed")
    
    # Read all entries
    entries = read_audit(100)
    
    assert len(entries) == 4
    
    # Verify first entry
    assert entries[0]["command"] == "init"
    assert entries[0]["result"] == "initialized"
    
    # Verify second entry
    assert entries[1]["command"] == "execute"
    assert entries[1]["args"] == {"param": "value"}
    assert entries[1]["result"] == "success"
    
    # Verify third entry
    assert entries[2]["command"] == "cleanup"
    
    # Verify fourth entry
    assert entries[3]["command"] == "error_op"
    assert entries[3]["error"] == "failed"
    
    # Verify chronological order
    timestamps = [datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")) 
                  for e in entries]
    assert timestamps == sorted(timestamps)


def test_integration_large_log_file(temp_history_dir, audit_file):
    """Integration: Handle large number of entries efficiently"""
    # Write 100 entries
    for i in range(100):
        log_operation(f"cmd_{i}", {"index": i}, f"result_{i}", None)
    
    # Read last 10
    entries = read_audit(10)
    
    assert len(entries) == 10
    assert entries[0]["command"] == "cmd_90"
    assert entries[-1]["command"] == "cmd_99"
    
    # Verify chronological order within last 10
    for i, entry in enumerate(entries):
        expected_idx = 90 + i
        assert entry["command"] == f"cmd_{expected_idx}"


def test_integration_mixed_optional_fields(temp_history_dir, audit_file):
    """Integration: Various combinations of optional fields"""
    test_cases = [
        ("cmd1", None, None, None),
        ("cmd2", {"a": 1}, None, None),
        ("cmd3", None, "result", None),
        ("cmd4", None, None, "error"),
        ("cmd5", {"b": 2}, "result", None),
        ("cmd6", {"c": 3}, None, "error"),
        ("cmd7", None, "result", "error"),
        ("cmd8", {"d": 4}, "result", "error"),
    ]
    
    for cmd, args, result, error in test_cases:
        log_operation(cmd, args, result, error)
    
    entries = read_audit(100)
    
    assert len(entries) == len(test_cases)
    
    for i, entry in enumerate(entries):
        cmd, args, result, error = test_cases[i]
        assert entry["command"] == cmd
        
        if args:
            assert entry.get("args") == args
        if result:
            assert entry.get("result") == result
        if error:
            assert entry.get("error") == error
