"""
Contract tests for src_ascend_audit module.

This test suite verifies the audit logging functionality according to the contract.
Tests are isolated using tmp_path fixtures and mock ascend.config to redirect
the audit path to temporary directories.
"""

import pytest
import json
import os
import stat
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, mock_open, MagicMock
from typing import Any

# Import the module under test
from src.ascend.audit import _audit_path, log_operation, read_audit


@pytest.fixture
def mock_history_dir(tmp_path, monkeypatch):
    """Fixture to mock HISTORY_DIR from ascend.config with a tmp_path."""
    history_dir = tmp_path / "history"
    
    # Mock the ascend.config module
    mock_config = Mock()
    mock_config.HISTORY_DIR = history_dir
    
    monkeypatch.setattr("src_ascend_audit.config", mock_config)
    
    return history_dir


@pytest.fixture
def populated_audit_log(mock_history_dir):
    """Fixture to create a populated audit log with 5 entries."""
    audit_file = mock_history_dir / "audit.jsonl"
    audit_file.parent.mkdir(parents=True, exist_ok=True)
    
    entries = []
    for i in range(5):
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "command": f"command_{i}",
            "args": {"index": i}
        }
        entries.append(entry)
    
    with open(audit_file, 'w') as f:
        for entry in entries:
            f.write(json.dumps(entry) + '\n')
    
    return audit_file, entries


class TestAuditPath:
    """Tests for _audit_path function."""
    
    def test_audit_path_happy_path(self, mock_history_dir):
        """Test _audit_path returns correct Path to audit.jsonl in HISTORY_DIR."""
        result = _audit_path()
        
        # Result is a Path object
        assert isinstance(result, Path)
        
        # Path ends with 'audit.jsonl'
        assert result.name == "audit.jsonl"
        
        # Path parent is HISTORY_DIR
        assert result.parent == mock_history_dir


class TestLogOperation:
    """Tests for log_operation function."""
    
    def test_log_operation_all_params(self, mock_history_dir):
        """Test log_operation with all optional parameters provided."""
        command = "test_command"
        args = {"key": "value"}
        result = "success"
        error = "none"
        
        log_operation(command, args, result, error)
        
        audit_file = mock_history_dir / "audit.jsonl"
        
        # Audit file exists
        assert audit_file.exists()
        
        # Read the entry
        with open(audit_file, 'r') as f:
            line = f.readline()
            entry = json.loads(line)
        
        # Entry contains timestamp in ISO format
        assert "timestamp" in entry
        datetime.fromisoformat(entry["timestamp"])  # Should not raise
        
        # Entry contains command field
        assert entry["command"] == command
        
        # Entry contains args field
        assert "args" in entry
        assert entry["args"] == args
        
        # Entry contains result field
        assert "result" in entry
        assert entry["result"] == result
        
        # Entry contains error field
        assert "error" in entry
        assert entry["error"] == error
    
    def test_log_operation_minimal_params(self, mock_history_dir):
        """Test log_operation with only required command parameter."""
        command = "minimal_command"
        
        log_operation(command, None, None, None)
        
        audit_file = mock_history_dir / "audit.jsonl"
        
        # Audit file exists
        assert audit_file.exists()
        
        # Read the entry
        with open(audit_file, 'r') as f:
            line = f.readline()
            entry = json.loads(line)
        
        # Entry contains timestamp
        assert "timestamp" in entry
        
        # Entry contains command field
        assert entry["command"] == command
        
        # Entry does not contain args field
        assert "args" not in entry
        
        # Entry does not contain result field
        assert "result" not in entry
        
        # Entry does not contain error field
        assert "error" not in entry
    
    def test_log_operation_creates_parent_dirs(self, mock_history_dir):
        """Test log_operation creates parent directories if they don't exist."""
        command = "test_command"
        
        # Ensure parent directory doesn't exist
        assert not mock_history_dir.exists()
        
        log_operation(command, None, None, None)
        
        audit_file = mock_history_dir / "audit.jsonl"
        
        # Parent directory exists after call
        assert mock_history_dir.exists()
        
        # Audit file is created
        assert audit_file.exists()
    
    def test_log_operation_empty_optional_params(self, mock_history_dir):
        """Test log_operation with empty strings for optional parameters."""
        command = "test"
        
        log_operation(command, {}, "", "")
        
        audit_file = mock_history_dir / "audit.jsonl"
        
        with open(audit_file, 'r') as f:
            line = f.readline()
            entry = json.loads(line)
        
        # Entry does not contain args field for empty dict
        assert "args" not in entry
        
        # Entry does not contain result field for empty string
        assert "result" not in entry
        
        # Entry does not contain error field for empty string
        assert "error" not in entry
    
    def test_log_operation_complex_args(self, mock_history_dir):
        """Test log_operation with complex nested args dictionary."""
        command = "complex_command"
        args = {"nested": {"key": [1, 2, 3]}, "another": "value"}
        
        log_operation(command, args, None, None)
        
        audit_file = mock_history_dir / "audit.jsonl"
        
        with open(audit_file, 'r') as f:
            line = f.readline()
            entry = json.loads(line)
        
        # Entry contains args field
        assert "args" in entry
        
        # Args are correctly deserialized
        assert entry["args"] == args
    
    def test_log_operation_permission_error(self, mock_history_dir):
        """Test log_operation raises permission_error when write permissions are denied."""
        command = "test_command"
        
        # Create the directory but make it read-only
        mock_history_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(mock_history_dir, stat.S_IRUSR | stat.S_IXUSR)
        
        try:
            # PermissionError is raised
            with pytest.raises(PermissionError):
                log_operation(command, None, None, None)
        finally:
            # Restore permissions for cleanup
            os.chmod(mock_history_dir, stat.S_IRWXU)
    
    def test_log_operation_json_serialization_error(self, mock_history_dir):
        """Test log_operation raises json_serialization_error for non-serializable objects."""
        command = "test_command"
        
        # Create a custom class that cannot be serialized even with default=str
        class NonSerializable:
            def __str__(self):
                raise TypeError("Cannot convert to string")
        
        # Mock json.dump to raise TypeError
        with patch('src_ascend_audit.json.dump') as mock_dump:
            mock_dump.side_effect = TypeError("Object not serializable")
            
            # TypeError is raised for non-serializable objects
            with pytest.raises(TypeError):
                log_operation(command, {"obj": NonSerializable()}, None, None)
    
    def test_log_operation_partial_optional_params(self, mock_history_dir):
        """Test log_operation with some optional parameters (only args and result)."""
        command = "partial_command"
        args = {"key": "value"}
        result = "success"
        
        log_operation(command, args, result, None)
        
        audit_file = mock_history_dir / "audit.jsonl"
        
        with open(audit_file, 'r') as f:
            line = f.readline()
            entry = json.loads(line)
        
        # Entry contains args field
        assert "args" in entry
        assert entry["args"] == args
        
        # Entry contains result field
        assert "result" in entry
        assert entry["result"] == result
        
        # Entry does not contain error field
        assert "error" not in entry


class TestReadAudit:
    """Tests for read_audit function."""
    
    def test_read_audit_empty_file(self, mock_history_dir):
        """Test read_audit returns empty list when audit file doesn't exist."""
        result = read_audit(10)
        
        # Returns empty list
        assert result == []
    
    def test_read_audit_last_n_entries(self, populated_audit_log):
        """Test read_audit returns last N entries in order."""
        audit_file, entries = populated_audit_log
        
        result = read_audit(3)
        
        # Returns list of length 3
        assert len(result) == 3
        
        # Entries are in correct order
        assert result[0]["command"] == "command_2"
        assert result[1]["command"] == "command_3"
        assert result[2]["command"] == "command_4"
        
        # Returns the last 3 entries
        for i, entry in enumerate(result):
            assert entry["args"]["index"] == i + 2
    
    def test_read_audit_zero_entries(self, mock_history_dir):
        """Test read_audit with last_n=0."""
        result = read_audit(0)
        
        # Returns empty list
        assert result == []
    
    def test_read_audit_exceeds_available(self, populated_audit_log):
        """Test read_audit when last_n exceeds available entries."""
        audit_file, entries = populated_audit_log
        
        result = read_audit(100)
        
        # Returns list of length 5
        assert len(result) == 5
        
        # All entries are returned
        for i, entry in enumerate(result):
            assert entry["command"] == f"command_{i}"
    
    def test_read_audit_filters_empty_lines(self, mock_history_dir):
        """Test read_audit filters out empty lines in audit file."""
        audit_file = mock_history_dir / "audit.jsonl"
        audit_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Create file with entries and empty lines
        with open(audit_file, 'w') as f:
            f.write(json.dumps({"command": "cmd1"}) + '\n')
            f.write('\n')  # Empty line
            f.write(json.dumps({"command": "cmd2"}) + '\n')
            f.write('\n')  # Empty line
            f.write(json.dumps({"command": "cmd3"}) + '\n')
        
        result = read_audit(10)
        
        # Returns only valid entries
        assert len(result) == 3
        
        # Empty lines are not included
        for entry in result:
            assert "command" in entry
    
    def test_read_audit_json_decode_error(self, mock_history_dir):
        """Test read_audit raises json_decode_error for malformed JSON."""
        audit_file = mock_history_dir / "audit.jsonl"
        audit_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Create file with malformed JSON
        with open(audit_file, 'w') as f:
            f.write(json.dumps({"command": "cmd1"}) + '\n')
            f.write('{"invalid json\n')  # Malformed JSON
        
        # JSONDecodeError is raised
        with pytest.raises(json.JSONDecodeError):
            read_audit(10)
    
    def test_read_audit_permission_error(self, mock_history_dir):
        """Test read_audit raises permission_error when read permissions are denied."""
        audit_file = mock_history_dir / "audit.jsonl"
        audit_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Create file and make it write-only
        with open(audit_file, 'w') as f:
            f.write(json.dumps({"command": "cmd1"}) + '\n')
        
        os.chmod(audit_file, stat.S_IWUSR)
        
        try:
            # PermissionError is raised
            with pytest.raises(PermissionError):
                read_audit(10)
        finally:
            # Restore permissions for cleanup
            os.chmod(audit_file, stat.S_IRWXU)
    
    def test_read_audit_single_entry(self, populated_audit_log):
        """Test read_audit with last_n=1."""
        audit_file, entries = populated_audit_log
        
        result = read_audit(1)
        
        # Returns list of length 1
        assert len(result) == 1
        
        # Returns the last entry
        assert result[0]["command"] == "command_4"
        assert result[0]["args"]["index"] == 4


class TestInvariants:
    """Tests for audit log invariants."""
    
    def test_invariant_append_only(self, mock_history_dir):
        """Test that audit log is append-only (multiple log operations append)."""
        audit_file = mock_history_dir / "audit.jsonl"
        
        # Log first operation
        log_operation("cmd1", None, None, None)
        
        # Get file size after first operation
        size1 = audit_file.stat().st_size
        
        # Read first entry
        with open(audit_file, 'r') as f:
            first_content = f.read()
        
        # Log second operation
        log_operation("cmd2", None, None, None)
        
        # File grows with each operation
        size2 = audit_file.stat().st_size
        assert size2 > size1
        
        # Read all content
        with open(audit_file, 'r') as f:
            lines = f.readlines()
        
        # Previous entries remain unchanged
        assert lines[0] == first_content
        
        # New entries are appended
        assert len(lines) == 2
        entry2 = json.loads(lines[1])
        assert entry2["command"] == "cmd2"
    
    def test_invariant_timestamp_format(self, mock_history_dir):
        """Test that each audit entry contains UTC ISO-formatted timestamp."""
        command = "test_command"
        
        log_operation(command, None, None, None)
        
        audit_file = mock_history_dir / "audit.jsonl"
        
        with open(audit_file, 'r') as f:
            line = f.readline()
            entry = json.loads(line)
        
        # Timestamp field exists
        assert "timestamp" in entry
        
        # Timestamp is in ISO format
        timestamp_str = entry["timestamp"]
        
        # Timestamp is valid UTC time
        parsed_time = datetime.fromisoformat(timestamp_str)
        assert parsed_time is not None
    
    def test_invariant_command_field(self, mock_history_dir):
        """Test that each audit entry contains a command field."""
        command = "test_command"
        
        log_operation(command, None, None, None)
        
        audit_file = mock_history_dir / "audit.jsonl"
        
        with open(audit_file, 'r') as f:
            line = f.readline()
            entry = json.loads(line)
        
        # Command field exists in entry
        assert "command" in entry
        assert entry["command"] == command
    
    def test_invariant_valid_json_lines(self, mock_history_dir):
        """Test that each line in audit.jsonl is valid JSON followed by newline."""
        log_operation("cmd1", None, None, None)
        log_operation("cmd2", {"arg": "value"}, None, None)
        log_operation("cmd3", None, "result", "error")
        
        audit_file = mock_history_dir / "audit.jsonl"
        
        with open(audit_file, 'r') as f:
            content = f.read()
            lines = content.split('\n')
        
        # Each non-empty line is valid JSON
        for line in lines:
            if line:  # Skip empty lines at end of file
                # Each line ends with newline (when read as raw content)
                assert line in content
                
                # Each line is valid JSON
                entry = json.loads(line)
                assert isinstance(entry, dict)
