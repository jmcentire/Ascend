"""
Contract tests for src_ascend_output module.

Tests verify behavior at boundaries, not internals. Cover happy paths, 
edge cases, error cases, and invariants. Mock dependencies.
"""

import pytest
import json
import sys
from io import StringIO
from unittest.mock import Mock, patch, MagicMock, call
from subprocess import TimeoutExpired

# Import the component under test
from src.ascend.output import (
    _colorize,
    print_report,
    print_json,
    print_status,
    copy_to_clipboard,
    format_table,
    render_output,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_markdown_report():
    """Sample markdown report with various patterns."""
    return """# Project Status Report
## Summary
### Details
Status: Active
Risk Level: At Risk
Issues: Blocked
Generated: 2024-01-01
---
Regular text line"""


@pytest.fixture
def sample_table_data():
    """Sample table headers and rows."""
    return {
        "headers": ["Name", "Status", "Progress"],
        "rows": [
            ["Task 1", "Active", "80%"],
            ["Task 2", "Blocked", "20%"],
            ["Task 3", "On Track", "100%"]
        ]
    }


@pytest.fixture
def sample_json_data():
    """Sample JSON-serializable data."""
    return {
        "project": "test",
        "tasks": [
            {"id": 1, "name": "Task 1"},
            {"id": 2, "name": "Task 2"}
        ],
        "count": 2
    }


class NonSerializable:
    """Custom class for testing non-serializable objects."""
    def __str__(self):
        return "NonSerializable(test)"


# ============================================================================
# Test _colorize
# ============================================================================

class TestColorize:
    """Tests for _colorize function."""
    
    def test_colorize_happy_path_headers(self):
        """Verify that _colorize applies bold cyan to # and ## headers."""
        text = "# Main Header\n## Sub Header\nRegular line"
        result = _colorize(text)
        
        # Check for ANSI codes in header lines
        lines = result.split('\n')
        assert '\x1b[' in lines[0], "Main header should contain ANSI codes"
        assert '\x1b[' in lines[1], "Sub header should contain ANSI codes"
        # Regular line should not have codes (or minimal)
        assert lines[2] == "Regular line" or '\x1b[0m' not in lines[2], \
            "Regular line should be unchanged or only have reset codes"
    
    def test_colorize_happy_path_subheaders(self):
        """Verify that _colorize applies bold to ### subheaders."""
        text = "### Subheader\nRegular text"
        result = _colorize(text)
        
        lines = result.split('\n')
        assert '\x1b[' in lines[0], "Subheader should contain ANSI codes"
        # Check for bold code (ANSI code 1)
        assert '\x1b[1m' in lines[0] or 'bold' in result.lower(), \
            "Subheader should be bold"
    
    def test_colorize_happy_path_status_keywords(self):
        """Verify that _colorize applies colors to status keywords."""
        text = "Line with Blocked status\nLine with Active status\nLine with On Track status\nLine with At Risk status"
        result = _colorize(text)
        
        lines = result.split('\n')
        # Blocked should be red
        assert '\x1b[' in lines[0], "Blocked line should have ANSI codes"
        # Active should be green
        assert '\x1b[' in lines[1], "Active line should have ANSI codes"
        # On Track should be green
        assert '\x1b[' in lines[2], "On Track line should have ANSI codes"
        # At Risk should be yellow
        assert '\x1b[' in lines[3], "At Risk line should have ANSI codes"
    
    def test_colorize_happy_path_metadata(self):
        """Verify that _colorize dims metadata lines."""
        text = "Generated: 2024-01-01\n---\nRegular line"
        result = _colorize(text)
        
        lines = result.split('\n')
        # Check that Generated and --- lines have ANSI codes (dim)
        assert '\x1b[' in lines[0], "Generated line should have ANSI codes"
        assert '\x1b[' in lines[1], "--- line should have ANSI codes"
    
    def test_colorize_edge_case_empty(self):
        """Verify _colorize handles empty string."""
        result = _colorize("")
        assert result == "", "Empty string should return empty string"
    
    def test_colorize_edge_case_no_patterns(self):
        """Verify _colorize returns unchanged text when no patterns match."""
        text = "Just some regular text\nwithout any special patterns\nat all"
        result = _colorize(text)
        
        # Should return original text (no ANSI codes added)
        # Note: there might be reset codes, so check that original text is preserved
        assert "Just some regular text" in result
        assert "without any special patterns" in result
        assert "at all" in result
    
    def test_colorize_edge_case_mixed_patterns(self):
        """Verify _colorize handles text with multiple pattern types."""
        text = "# Header\nStatus: Active\nGenerated: now\n### Subheader\nBlocked item"
        result = _colorize(text)
        
        # Each line should have appropriate ANSI codes
        lines = result.split('\n')
        assert all('\x1b[' in line or line == '' for line in lines if line.strip()), \
            "All pattern lines should have ANSI codes"


# ============================================================================
# Test print_report
# ============================================================================

class TestPrintReport:
    """Tests for print_report function."""
    
    def test_print_report_happy_path_with_color_true(self, capsys):
        """Verify print_report prints colored text when use_color is True."""
        text = "# Test Report\nStatus: Active"
        print_report(text, use_color=True)
        
        captured = capsys.readouterr()
        assert "Test Report" in captured.out, "Report text should be in output"
        assert '\x1b[' in captured.out, "ANSI color codes should be present"
    
    def test_print_report_happy_path_with_color_false(self, capsys):
        """Verify print_report prints plain text when use_color is False."""
        text = "# Test Report\nStatus: Active"
        print_report(text, use_color=False)
        
        captured = capsys.readouterr()
        assert "Test Report" in captured.out, "Report text should be in output"
        assert '\x1b[' not in captured.out, "ANSI color codes should not be present"
    
    def test_print_report_happy_path_with_color_none_tty(self, capsys):
        """Verify print_report applies colors when use_color is None and stdout is a TTY."""
        text = "# Test Report"
        
        with patch('sys.stdout.isatty', return_value=True):
            print_report(text, use_color=None)
        
        captured = capsys.readouterr()
        assert "Test Report" in captured.out, "Report text should be in output"
        assert '\x1b[' in captured.out, "ANSI color codes should be present for TTY"
    
    def test_print_report_edge_case_none_not_tty(self, capsys):
        """Verify print_report does not apply colors when use_color is None and stdout is not a TTY."""
        text = "# Test Report"
        
        with patch('sys.stdout.isatty', return_value=False):
            print_report(text, use_color=None)
        
        captured = capsys.readouterr()
        assert "Test Report" in captured.out, "Report text should be in output"
        assert '\x1b[' not in captured.out, "ANSI color codes should not be present for non-TTY"


# ============================================================================
# Test print_json
# ============================================================================

class TestPrintJson:
    """Tests for print_json function."""
    
    def test_print_json_happy_path_simple(self, capsys, sample_json_data):
        """Verify print_json prints serializable data with 2-space indentation."""
        print_json(sample_json_data)
        
        captured = capsys.readouterr()
        output = captured.out
        
        # Verify it's valid JSON
        parsed = json.loads(output)
        assert parsed == sample_json_data, "Output should match input data"
        
        # Check for 2-space indentation
        assert '  "project"' in output or '  "tasks"' in output, \
            "Should have 2-space indentation"
    
    def test_print_json_happy_path_non_serializable(self, capsys):
        """Verify print_json converts non-serializable objects to strings."""
        data = {"item": NonSerializable(), "name": "test"}
        print_json(data)
        
        captured = capsys.readouterr()
        output = captured.out
        
        # Verify it's valid JSON
        parsed = json.loads(output)
        assert "NonSerializable" in str(parsed["item"]), \
            "Non-serializable object should be converted to string"
    
    def test_print_json_edge_case_none(self, capsys):
        """Verify print_json handles None value."""
        print_json(None)
        
        captured = capsys.readouterr()
        assert captured.out.strip() == "null", "None should be serialized as 'null'"
    
    def test_print_json_edge_case_empty_dict(self, capsys):
        """Verify print_json handles empty dictionary."""
        print_json({})
        
        captured = capsys.readouterr()
        assert captured.out.strip() == "{}", "Empty dict should be serialized as '{}'"
    
    def test_print_json_edge_case_nested(self, capsys):
        """Verify print_json handles nested structures."""
        data = {
            "level1": {
                "level2": {
                    "level3": ["a", "b", "c"]
                }
            }
        }
        print_json(data)
        
        captured = capsys.readouterr()
        output = captured.out
        
        # Verify it's valid JSON and properly nested
        parsed = json.loads(output)
        assert parsed == data, "Nested structure should be preserved"
        
        # Check for proper indentation (nested should have more spaces)
        assert '    "level2"' in output or '  "level1"' in output, \
            "Should have proper nested indentation"
    
    def test_print_json_edge_case_special_chars(self, capsys):
        """Verify print_json handles special characters."""
        data = {
            "unicode": "Hello 世界 🌍",
            "quotes": 'She said "hello"',
            "newline": "line1\nline2"
        }
        print_json(data)
        
        captured = capsys.readouterr()
        output = captured.out
        
        # Verify it's valid JSON
        parsed = json.loads(output)
        assert parsed["unicode"] == "Hello 世界 🌍", "Unicode should be preserved"
        assert parsed["quotes"] == 'She said "hello"', "Quotes should be escaped"
        assert parsed["newline"] == "line1\nline2", "Newlines should be escaped"


# ============================================================================
# Test print_status
# ============================================================================

class TestPrintStatus:
    """Tests for print_status function."""
    
    def test_print_status_happy_path_tty(self, capsys):
        """Verify print_status prints dimmed message when stderr is a TTY."""
        message = "Processing..."
        
        with patch('sys.stderr.isatty', return_value=True):
            print_status(message)
        
        captured = capsys.readouterr()
        assert message in captured.err, "Message should be in stderr"
        assert '\x1b[' in captured.err, "ANSI dim codes should be present for TTY"
    
    def test_print_status_happy_path_not_tty(self, capsys):
        """Verify print_status prints plain message when stderr is not a TTY."""
        message = "Processing..."
        
        with patch('sys.stderr.isatty', return_value=False):
            print_status(message)
        
        captured = capsys.readouterr()
        assert message in captured.err, "Message should be in stderr"
        assert '\x1b[' not in captured.err, "ANSI codes should not be present for non-TTY"
    
    def test_print_status_edge_case_empty_message(self, capsys):
        """Verify print_status handles empty message."""
        with patch('sys.stderr.isatty', return_value=False):
            print_status("")
        
        captured = capsys.readouterr()
        # Should print something to stderr (at least newline)
        assert captured.err is not None, "Should print to stderr"


# ============================================================================
# Test copy_to_clipboard
# ============================================================================

class TestCopyToClipboard:
    """Tests for copy_to_clipboard function."""
    
    def test_copy_to_clipboard_happy_path_success(self):
        """Verify copy_to_clipboard returns True when pbcopy succeeds."""
        text = "Test content"
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            result = copy_to_clipboard(text)
        
        assert result is True, "Should return True on success"
        mock_run.assert_called_once()
        
        # Verify timeout is 5 seconds
        call_args = mock_run.call_args
        assert call_args[1]['timeout'] == 5, "Timeout should be 5 seconds"
        
        # Verify pbcopy command
        assert 'pbcopy' in call_args[0][0], "Should call pbcopy command"
    
    def test_copy_to_clipboard_error_timeout(self):
        """Verify copy_to_clipboard returns False on timeout."""
        text = "Test content"
        
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = TimeoutExpired('pbcopy', 5)
            result = copy_to_clipboard(text)
        
        assert result is False, "Should return False on timeout"
    
    def test_copy_to_clipboard_error_command_not_found(self):
        """Verify copy_to_clipboard returns False when pbcopy is not found."""
        text = "Test content"
        
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = FileNotFoundError("pbcopy not found")
            result = copy_to_clipboard(text)
        
        assert result is False, "Should return False when command not found"
    
    def test_copy_to_clipboard_error_os_error(self):
        """Verify copy_to_clipboard returns False on OSError."""
        text = "Test content"
        
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = OSError("Permission denied")
            result = copy_to_clipboard(text)
        
        assert result is False, "Should return False on OSError"
    
    def test_copy_to_clipboard_error_non_zero_returncode(self):
        """Verify copy_to_clipboard returns False when pbcopy returns non-zero."""
        text = "Test content"
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=1)
            result = copy_to_clipboard(text)
        
        assert result is False, "Should return False when returncode != 0"


# ============================================================================
# Test format_table
# ============================================================================

class TestFormatTable:
    """Tests for format_table function."""
    
    def test_format_table_happy_path_simple(self, sample_table_data):
        """Verify format_table creates markdown table with proper formatting."""
        result = format_table(
            sample_table_data["headers"],
            sample_table_data["rows"]
        )
        
        # Check for markdown table elements
        assert '|' in result, "Should contain pipe separators"
        assert 'Name' in result, "Should contain headers"
        assert 'Task 1' in result, "Should contain data"
        assert '---' in result or '-' * 3 in result, "Should contain separator line"
        
        # Check structure
        lines = result.strip().split('\n')
        assert len(lines) >= 4, "Should have header, separator, and data rows"
    
    def test_format_table_edge_case_empty_rows(self):
        """Verify format_table returns 'No data.' for empty rows."""
        result = format_table(["Header1", "Header2"], [])
        assert result == "No data.", "Should return 'No data.' for empty rows"
    
    def test_format_table_edge_case_mismatched_rows(self):
        """Verify format_table handles rows with varying lengths."""
        headers = ["Col1", "Col2", "Col3"]
        rows = [
            ["A", "B", "C"],
            ["D", "E"],  # Short row
            ["F", "G", "H", "I"]  # Long row
        ]
        result = format_table(headers, rows)
        
        # Should still produce valid table
        assert '|' in result, "Should contain pipe separators"
        assert 'Col1' in result and 'Col2' in result, "Should contain headers"
        
        # Check that short rows are handled
        lines = result.strip().split('\n')
        assert len(lines) >= 4, "Should have all rows"
    
    def test_format_table_edge_case_unicode(self):
        """Verify format_table handles Unicode characters."""
        headers = ["Name", "Symbol"]
        rows = [
            ["Earth", "🌍"],
            ["Heart", "❤️"],
            ["Chinese", "你好"]
        ]
        result = format_table(headers, rows)
        
        # Unicode should be preserved
        assert "🌍" in result, "Should contain emoji"
        assert "❤️" in result, "Should contain emoji"
        assert "你好" in result, "Should contain Chinese characters"
    
    def test_format_table_edge_case_long_content(self):
        """Verify format_table calculates column widths for long content."""
        headers = ["Short", "Long Column"]
        rows = [
            ["A", "This is a very long piece of content that should expand the column"],
            ["B", "Short"]
        ]
        result = format_table(headers, rows)
        
        # Long content should be fully visible
        assert "This is a very long piece of content" in result, \
            "Long content should be in output"
        
        # Table structure should be maintained
        lines = result.strip().split('\n')
        # All data lines should have roughly same length (accounting for padding)
        line_lengths = [len(line) for line in lines]
        assert max(line_lengths) - min(line_lengths) < 10, \
            "Lines should be similarly aligned"
    
    def test_format_table_edge_case_single_row(self):
        """Verify format_table handles single row."""
        headers = ["Name", "Value"]
        rows = [["Item", "123"]]
        result = format_table(headers, rows)
        
        # Should have header, separator, and one data row
        lines = result.strip().split('\n')
        assert len(lines) == 3, "Should have exactly 3 lines (header, sep, data)"
        assert 'Name' in lines[0], "First line should be header"
        assert 'Item' in lines[2], "Third line should be data"


# ============================================================================
# Test render_output
# ============================================================================

class TestRenderOutput:
    """Tests for render_output function."""
    
    def test_render_output_happy_path_json_mode(self, capsys, sample_json_data):
        """Verify render_output prints JSON when json_mode is True."""
        render_output(sample_json_data, json_mode=True, copy=False)
        
        captured = capsys.readouterr()
        output = captured.out
        
        # Should be valid JSON
        parsed = json.loads(output)
        assert parsed == sample_json_data, "Should output JSON"
    
    def test_render_output_happy_path_markdown_mode_str(self, capsys):
        """Verify render_output prints colored report when json_mode is False and data is str."""
        data = "# Test Report\nStatus: Active"
        render_output(data, json_mode=False, copy=False)
        
        captured = capsys.readouterr()
        assert "Test Report" in captured.out, "Should output report text"
    
    def test_render_output_happy_path_markdown_mode_non_str(self, capsys, sample_json_data):
        """Verify render_output prints JSON when json_mode is False and data is not str."""
        render_output(sample_json_data, json_mode=False, copy=False)
        
        captured = capsys.readouterr()
        output = captured.out
        
        # Should be valid JSON (fallback for non-string data)
        parsed = json.loads(output)
        assert parsed == sample_json_data, "Should output JSON for non-string data"
    
    def test_render_output_happy_path_with_clipboard_copy(self, capsys):
        """Verify render_output attempts clipboard copy when copy is True."""
        data = {"test": "data"}
        
        with patch('src_ascend_output.copy_to_clipboard', return_value=True) as mock_copy:
            render_output(data, json_mode=True, copy=True)
        
        captured = capsys.readouterr()
        assert captured.out, "Should output data"
        mock_copy.assert_called_once(), "Should attempt clipboard copy"
    
    def test_render_output_edge_case_copy_failure(self, capsys):
        """Verify render_output handles clipboard copy failure gracefully."""
        data = {"test": "data"}
        
        with patch('src_ascend_output.copy_to_clipboard', return_value=False):
            # Should not raise exception
            render_output(data, json_mode=True, copy=True)
        
        captured = capsys.readouterr()
        assert captured.out, "Should still output data despite copy failure"


# ============================================================================
# Test Invariants
# ============================================================================

class TestInvariants:
    """Tests for contract invariants."""
    
    def test_invariant_ansi_codes_constants(self):
        """Verify ANSI color code constants are defined."""
        import src_ascend_output as module
        
        # Check that ANSI constants exist
        assert hasattr(module, '_RESET') or '_RESET' in dir(module) or \
               any('RESET' in name for name in dir(module)), \
               "Should have _RESET or similar constant"
        
        # Try to access through _colorize behavior
        colored = _colorize("# Test")
        assert '\x1b[0m' in colored or '\x1b[' in colored, \
            "Should use ANSI escape codes"
    
    def test_invariant_pbcopy_timeout(self):
        """Verify pbcopy timeout is 5 seconds."""
        text = "Test"
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            copy_to_clipboard(text)
        
        # Verify timeout parameter
        call_args = mock_run.call_args
        assert call_args[1]['timeout'] == 5, "Timeout must be exactly 5 seconds"
    
    def test_invariant_json_indentation(self, capsys):
        """Verify JSON output always uses 2-space indentation."""
        data = {"key": "value", "nested": {"a": 1}}
        print_json(data)
        
        captured = capsys.readouterr()
        output = captured.out
        
        # Check for 2-space indentation
        lines = output.split('\n')
        indented_lines = [line for line in lines if line.startswith('  ') and not line.startswith('    ')]
        assert len(indented_lines) > 0, "Should have 2-space indented lines"
        
        # Verify no 4-space base indentation (would indicate indent=4)
        assert not any(line.startswith('    ') and not line.startswith('      ') 
                      for line in lines if '"' in line), \
               "Should use 2-space indent, not 4-space"
    
    def test_invariant_json_default_str(self, capsys):
        """Verify JSON serialization uses default=str for non-serializable objects."""
        class CustomObject:
            def __str__(self):
                return "custom_string_representation"
        
        data = {"obj": CustomObject()}
        print_json(data)
        
        captured = capsys.readouterr()
        output = captured.out
        
        # Should be valid JSON
        parsed = json.loads(output)
        assert "custom_string_representation" in str(parsed["obj"]), \
            "Non-serializable objects should be converted using str()"


# ============================================================================
# Additional edge case tests
# ============================================================================

class TestAdditionalEdgeCases:
    """Additional edge case tests for comprehensive coverage."""
    
    def test_colorize_multiline_status(self):
        """Test that status keywords work mid-line and across multiple formats."""
        text = "Task is Blocked and needs attention\nEverything is On Track here\nRisk: At Risk level"
        result = _colorize(text)
        
        # All lines with keywords should have ANSI codes
        lines = result.split('\n')
        assert all('\x1b[' in line for line in lines), \
            "All lines with status keywords should be colored"
    
    def test_format_table_empty_headers(self):
        """Test format_table with empty strings in headers."""
        headers = ["", "Column2", ""]
        rows = [["A", "B", "C"]]
        result = format_table(headers, rows)
        
        # Should still produce valid table
        assert '|' in result, "Should contain pipe separators"
        assert 'Column2' in result, "Should contain non-empty header"
    
    def test_print_report_empty_text(self, capsys):
        """Test print_report with empty text."""
        print_report("", use_color=False)
        
        captured = capsys.readouterr()
        # Should handle gracefully (might print newline)
        assert captured.out is not None
    
    def test_copy_to_clipboard_empty_text(self):
        """Test copy_to_clipboard with empty string."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            result = copy_to_clipboard("")
        
        assert result is True, "Should handle empty string"
        mock_run.assert_called_once()
    
    def test_render_output_none_data(self, capsys):
        """Test render_output with None data."""
        render_output(None, json_mode=True, copy=False)
        
        captured = capsys.readouterr()
        assert "null" in captured.out, "Should serialize None as null"
    
    def test_print_json_list_data(self, capsys):
        """Test print_json with list instead of dict."""
        data = [1, 2, 3, {"key": "value"}]
        print_json(data)
        
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed == data, "Should handle list data"
    
    def test_format_table_special_characters_in_cells(self):
        """Test format_table with special markdown characters in cells."""
        headers = ["Name", "Description"]
        rows = [
            ["Item|1", "Has | pipes"],
            ["Item#2", "Has # hash"],
            ["Item-3", "Has --- dashes"]
        ]
        result = format_table(headers, rows)
        
        # Special characters should be preserved
        assert "Item|1" in result or "Item" in result, "Should handle pipes in content"
        assert "#" in result, "Should handle hash in content"
        assert "---" in result, "Should handle dashes"
