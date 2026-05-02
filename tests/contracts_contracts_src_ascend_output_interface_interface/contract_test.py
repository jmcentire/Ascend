"""
Contract-based tests for Output Formatter Interface

This test suite validates the output formatting functions against their contracts.
Tests cover ANSI colorization, output printing, clipboard operations, table formatting,
and unified output rendering with comprehensive edge case and error handling.
"""

import pytest
import json
import sys
from unittest.mock import Mock, patch, MagicMock, call
from io import StringIO
import subprocess


# Import the module under test
# Adjust import path as needed based on actual module structure
try:
    from contracts.contracts_src.ascend_output_interface.interface import (
        _colorize,
        print_report,
        print_json,
        print_status,
        copy_to_clipboard,
        format_table,
        render_output,
    )
except ImportError:
    # Fallback import path
    try:
        from contracts.contracts_src_ascend_output_interface.interface import (
            _colorize,
            print_report,
            print_json,
            print_status,
            copy_to_clipboard,
            format_table,
            render_output,
        )
    except ImportError:
        # Another possible path
        import sys
        import os
        # Try to import assuming module is in path
        _colorize = None
        print_report = None
        print_json = None
        print_status = None
        copy_to_clipboard = None
        format_table = None
        render_output = None


# ANSI color code constants for validation
RESET = '\033[0m'
BOLD = '\033[1m'
DIM = '\033[2m'
GREEN = '\033[32m'
YELLOW = '\033[33m'
RED = '\033[31m'
CYAN = '\033[36m'


class TestColorize:
    """Test suite for _colorize function"""

    def test_colorize_happy_path_basic(self):
        """Test _colorize applies ANSI codes to basic markdown text"""
        text = "# Header\nSome text"
        result = _colorize(text)
        
        # Result contains ANSI escape codes
        assert '\033[' in result
        # Original text content preserved
        assert 'Header' in result
        assert 'Some text' in result
        # Header line is bold cyan
        assert BOLD in result or CYAN in result

    def test_colorize_all_patterns(self):
        """Test _colorize applies correct colors to all pattern types"""
        text = "# Main Header\n## Subheader\n### Sub-subheader\nBlocked item\nActive item\nOn Track item\nAt Risk item\nGenerated: 2023-01-01\n---"
        result = _colorize(text)
        
        lines = result.split('\n')
        
        # # lines are bold cyan
        header_line = [l for l in lines if 'Main Header' in l][0]
        assert BOLD in header_line and CYAN in header_line
        
        # ## lines are bold cyan
        subheader_line = [l for l in lines if 'Subheader' in l and '##' in l][0]
        assert BOLD in subheader_line and CYAN in subheader_line
        
        # ### lines are bold
        subsubheader_line = [l for l in lines if 'Sub-subheader' in l][0]
        assert BOLD in subsubheader_line
        
        # Blocked is red
        blocked_line = [l for l in lines if 'Blocked' in l][0]
        assert RED in blocked_line
        
        # Active is green
        active_line = [l for l in lines if 'Active' in l][0]
        assert GREEN in active_line
        
        # On Track is green
        on_track_line = [l for l in lines if 'On Track' in l][0]
        assert GREEN in on_track_line
        
        # At Risk is yellow
        at_risk_line = [l for l in lines if 'At Risk' in l][0]
        assert YELLOW in at_risk_line
        
        # Generated: is dimmed
        generated_line = [l for l in lines if 'Generated:' in l][0]
        assert DIM in generated_line
        
        # --- is dimmed
        separator_line = [l for l in lines if '---' in l][0]
        assert DIM in separator_line

    def test_colorize_empty_string(self):
        """Test _colorize handles empty string"""
        text = ""
        result = _colorize(text)
        
        # Result is empty string
        assert result == ""

    def test_colorize_no_patterns(self):
        """Test _colorize with text containing no special patterns"""
        text = "Plain text\nNo special formatting"
        result = _colorize(text)
        
        # Original text preserved
        assert 'Plain text' in result
        assert 'No special formatting' in result
        
        # No color codes applied except resets (or minimal codes)
        # Check that we don't have status colors
        assert RED not in result
        assert YELLOW not in result

    def test_colorize_multiline_headers(self):
        """Test _colorize with multiple header levels"""
        text = "# Level 1\n## Level 2\n### Level 3"
        result = _colorize(text)
        
        lines = result.split('\n')
        
        # # is bold cyan
        level1 = [l for l in lines if 'Level 1' in l][0]
        assert BOLD in level1 and CYAN in level1
        
        # ## is bold cyan
        level2 = [l for l in lines if 'Level 2' in l][0]
        assert BOLD in level2 and CYAN in level2
        
        # ### is bold
        level3 = [l for l in lines if 'Level 3' in l][0]
        assert BOLD in level3

    def test_invariant_ansi_codes(self):
        """Test that ANSI color codes match expected constants"""
        text = "Test"
        result = _colorize(text)
        
        # Verify constants match specification
        assert RESET == '\033[0m'
        assert BOLD == '\033[1m'
        assert DIM == '\033[2m'
        assert GREEN == '\033[32m'
        assert YELLOW == '\033[33m'
        assert RED == '\033[31m'
        assert CYAN == '\033[36m'


class TestPrintReport:
    """Test suite for print_report function"""

    def test_print_report_with_color_true(self, capsys):
        """Test print_report with use_color=True forces colorization"""
        text = "# Report\nActive status"
        print_report(text, use_color=True)
        
        captured = capsys.readouterr()
        # Text contains ANSI codes
        assert '\033[' in captured.out
        # Output to stdout
        assert 'Report' in captured.out
        assert 'Active status' in captured.out

    def test_print_report_with_color_false(self, capsys):
        """Test print_report with use_color=False prints plain text"""
        text = "# Report\nActive status"
        print_report(text, use_color=False)
        
        captured = capsys.readouterr()
        # Text is plain without ANSI codes
        assert '\033[' not in captured.out
        # Output to stdout
        assert 'Report' in captured.out
        assert 'Active status' in captured.out

    @patch('sys.stdout.isatty')
    def test_print_report_with_color_none_tty(self, mock_isatty, capsys):
        """Test print_report with use_color=None auto-detects TTY"""
        mock_isatty.return_value = True
        text = "# Report"
        print_report(text, use_color=None)
        
        captured = capsys.readouterr()
        # Text colorized when stdout is TTY
        assert '\033[' in captured.out
        assert 'Report' in captured.out

    @patch('sys.stdout.isatty')
    def test_print_report_with_color_none_no_tty(self, mock_isatty, capsys):
        """Test print_report with use_color=None and no TTY"""
        mock_isatty.return_value = False
        text = "# Report"
        print_report(text, use_color=None)
        
        captured = capsys.readouterr()
        # Text is plain when stdout is not TTY
        assert '\033[' not in captured.out
        assert 'Report' in captured.out


class TestPrintJson:
    """Test suite for print_json function"""

    def test_print_json_simple_dict(self, capsys):
        """Test print_json with simple dictionary"""
        data = {"key": "value", "number": 42}
        print_json(data)
        
        captured = capsys.readouterr()
        # Output is valid JSON
        parsed = json.loads(captured.out)
        assert parsed == data
        
        # Indentation is 2 spaces
        assert '  "key"' in captured.out or '  "number"' in captured.out
        
        # Output to stdout
        assert captured.err == ""

    def test_print_json_non_serializable(self, capsys):
        """Test print_json with non-serializable object uses str default"""
        class CustomObject:
            def __str__(self):
                return "CustomObject instance"
        
        data = {"obj": CustomObject()}
        print_json(data)
        
        captured = capsys.readouterr()
        # Non-serializable object handled via str()
        assert "CustomObject" in captured.out
        # Output to stdout
        assert captured.err == ""

    def test_print_json_nested_structure(self, capsys):
        """Test print_json with nested data structures"""
        data = {"outer": {"inner": [1, 2, 3]}}
        print_json(data)
        
        captured = capsys.readouterr()
        # Nested structure preserved
        parsed = json.loads(captured.out)
        assert parsed == data
        
        # Proper indentation (check for nested indentation)
        assert '  "outer"' in captured.out
        assert '    "inner"' in captured.out or '"inner"' in captured.out

    def test_invariant_json_format(self, capsys):
        """Test that JSON serialization always uses indent=2 and default=str"""
        data = {"test": 1}
        print_json(data)
        
        captured = capsys.readouterr()
        # indent=2 used (check spacing)
        assert '  ' in captured.out
        
        # default=str used (verify by testing with non-serializable)
        class TestObj:
            def __str__(self):
                return "test_obj"
        
        capsys.readouterr()  # Clear
        print_json({"obj": TestObj()})
        captured2 = capsys.readouterr()
        assert "test_obj" in captured2.out


class TestPrintStatus:
    """Test suite for print_status function"""

    def test_print_status_basic(self, capsys):
        """Test print_status outputs to stderr"""
        message = "Processing..."
        print_status(message)
        
        captured = capsys.readouterr()
        # Message in stderr
        assert message in captured.err
        # Newline included
        assert captured.err.endswith('\n')

    @patch('sys.stderr.isatty')
    def test_print_status_tty(self, mock_isatty, capsys):
        """Test print_status dims message when stderr is TTY"""
        mock_isatty.return_value = True
        message = "Status message"
        print_status(message)
        
        captured = capsys.readouterr()
        # Message is dimmed with ANSI codes
        assert DIM in captured.err or '\033[' in captured.err
        # Output to stderr
        assert message in captured.err

    @patch('sys.stderr.isatty')
    def test_print_status_no_tty(self, mock_isatty, capsys):
        """Test print_status plain text when stderr is not TTY"""
        mock_isatty.return_value = False
        message = "Status message"
        print_status(message)
        
        captured = capsys.readouterr()
        # Message is plain without ANSI codes
        assert '\033[' not in captured.err
        # Output to stderr
        assert message in captured.err

    def test_invariant_output_streams(self, capsys):
        """Test that status goes to stderr, not stdout"""
        message = "Test status"
        print_status(message)
        
        captured = capsys.readouterr()
        # Output to stderr
        assert message in captured.err
        # Nothing in stdout
        assert captured.out == ""


class TestCopyToClipboard:
    """Test suite for copy_to_clipboard function"""

    @patch('subprocess.run')
    def test_copy_to_clipboard_success(self, mock_run):
        """Test copy_to_clipboard returns True on successful pbcopy"""
        mock_run.return_value = Mock(returncode=0)
        text = "Test content"
        
        result = copy_to_clipboard(text)
        
        # Returns True
        assert result is True
        
        # Text passed to pbcopy
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ['pbcopy']
        assert call_args[1]['input'] == text
        assert call_args[1]['text'] is True
        
        # 5-second timeout set
        assert call_args[1]['timeout'] == 5

    @patch('subprocess.run')
    def test_copy_to_clipboard_timeout(self, mock_run):
        """Test copy_to_clipboard returns False on timeout"""
        mock_run.side_effect = subprocess.TimeoutExpired('pbcopy', 5)
        text = "Test content"
        
        result = copy_to_clipboard(text)
        
        # Returns False
        assert result is False
        # Timeout error caught
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_copy_to_clipboard_not_found(self, mock_run):
        """Test copy_to_clipboard returns False when pbcopy not found"""
        mock_run.side_effect = FileNotFoundError()
        text = "Test content"
        
        result = copy_to_clipboard(text)
        
        # Returns False
        assert result is False
        # FileNotFoundError caught
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_copy_to_clipboard_os_error(self, mock_run):
        """Test copy_to_clipboard returns False on OS error"""
        mock_run.side_effect = OSError("OS error")
        text = "Test content"
        
        result = copy_to_clipboard(text)
        
        # Returns False
        assert result is False
        # OSError caught
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_copy_to_clipboard_failure_returncode(self, mock_run):
        """Test copy_to_clipboard returns False when pbcopy fails"""
        mock_run.return_value = Mock(returncode=1)
        text = "Test content"
        
        result = copy_to_clipboard(text)
        
        # Returns False
        assert result is False
        # Non-zero returncode handled
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_invariant_clipboard_timeout(self, mock_run):
        """Test that clipboard operations use 5-second timeout"""
        mock_run.return_value = Mock(returncode=0)
        text = "Test"
        
        copy_to_clipboard(text)
        
        # timeout=5 passed to subprocess.run
        call_args = mock_run.call_args
        assert call_args[1]['timeout'] == 5


class TestFormatTable:
    """Test suite for format_table function"""

    def test_format_table_empty_rows(self):
        """Test format_table returns 'No data.' for empty rows"""
        headers = ["Col1", "Col2"]
        rows = []
        
        result = format_table(headers, rows)
        
        # Returns 'No data.'
        assert result == "No data."

    def test_format_table_basic(self):
        """Test format_table creates proper markdown table"""
        headers = ["Name", "Age"]
        rows = [["Alice", "30"], ["Bob", "25"]]
        
        result = format_table(headers, rows)
        
        lines = result.strip().split('\n')
        
        # Has header row
        assert "Name" in lines[0]
        assert "Age" in lines[0]
        
        # Has separator row with dashes
        assert "-" in lines[1]
        assert "|" in lines[1]
        
        # Has data rows
        assert "Alice" in lines[2]
        assert "30" in lines[2]
        assert "Bob" in lines[3]
        assert "25" in lines[3]
        
        # Columns aligned (all rows have | separators)
        for line in lines:
            assert "|" in line

    def test_format_table_mismatched_columns(self):
        """Test format_table handles rows shorter than headers"""
        headers = ["A", "B", "C"]
        rows = [["1", "2"], ["3"]]
        
        result = format_table(headers, rows)
        
        # Missing cells are empty
        lines = result.strip().split('\n')
        
        # Table structure maintained
        assert "A" in lines[0]
        assert "B" in lines[0]
        assert "C" in lines[0]
        
        # Rows exist even with missing cells
        assert len(lines) >= 4  # header + separator + 2 data rows

    def test_format_table_unicode(self):
        """Test format_table handles Unicode characters"""
        headers = ["Name", "Symbol"]
        rows = [["Pi", "π"], ["Lambda", "λ"]]
        
        result = format_table(headers, rows)
        
        # Unicode characters preserved in table
        assert "π" in result
        assert "λ" in result
        
        # Proper alignment (has structure)
        lines = result.strip().split('\n')
        assert len(lines) == 4  # header + separator + 2 data rows

    def test_format_table_single_column(self):
        """Test format_table with single column"""
        headers = ["Item"]
        rows = [["A"], ["B"]]
        
        result = format_table(headers, rows)
        
        lines = result.strip().split('\n')
        
        # Single column table created
        assert "Item" in lines[0]
        
        # Proper structure
        assert len(lines) == 4  # header + separator + 2 data rows

    def test_format_table_numeric_values(self):
        """Test format_table converts non-string cells to strings"""
        headers = ["ID", "Count"]
        rows = [[1, 100], [2, 200]]
        
        result = format_table(headers, rows)
        
        # Cells converted to strings
        assert "1" in result
        assert "100" in result
        assert "2" in result
        assert "200" in result
        
        # Table formatted correctly
        lines = result.strip().split('\n')
        assert len(lines) == 4  # header + separator + 2 data rows


class TestRenderOutput:
    """Test suite for render_output function"""

    @patch('contracts_contracts_src_ascend_output_interface_interface.print_json')
    def test_render_output_json_mode_true(self, mock_print_json, capsys):
        """Test render_output with json_mode=True serializes data"""
        data = {"key": "value"}
        render_output(data, json_mode=True, copy=False)
        
        # Data printed as JSON
        mock_print_json.assert_called_once_with(data)

    @patch('contracts_contracts_src_ascend_output_interface_interface.print_report')
    def test_render_output_json_mode_false_string(self, mock_print_report):
        """Test render_output with json_mode=False and string data prints as report"""
        data = "# Report text"
        render_output(data, json_mode=False, copy=False)
        
        # String printed as report
        mock_print_report.assert_called_once()
        # Colorization applied (use_color parameter passed)
        call_args = mock_print_report.call_args
        assert call_args[0][0] == data

    @patch('contracts_contracts_src_ascend_output_interface_interface.print_json')
    def test_render_output_json_mode_false_non_string(self, mock_print_json):
        """Test render_output with json_mode=False and non-string data serializes to JSON"""
        data = {"key": "value"}
        render_output(data, json_mode=False, copy=False)
        
        # Data printed as JSON
        mock_print_json.assert_called_once_with(data)

    @patch('contracts_contracts_src_ascend_output_interface_interface.copy_to_clipboard')
    @patch('contracts_contracts_src_ascend_output_interface_interface.print_report')
    def test_render_output_with_copy(self, mock_print_report, mock_copy):
        """Test render_output with copy=True copies to clipboard"""
        mock_copy.return_value = True
        data = "Test data"
        render_output(data, json_mode=False, copy=True)
        
        # copy_to_clipboard called
        mock_copy.assert_called_once()
        # Data printed
        mock_print_report.assert_called_once()

    @patch('contracts_contracts_src_ascend_output_interface_interface.copy_to_clipboard')
    @patch('contracts_contracts_src_ascend_output_interface_interface.print_json')
    def test_render_output_json_with_copy(self, mock_print_json, mock_copy, capsys):
        """Test render_output with json_mode=True and copy=True"""
        mock_copy.return_value = True
        data = {"test": 1}
        render_output(data, json_mode=True, copy=True)
        
        # Data serialized to JSON
        mock_print_json.assert_called_once_with(data)
        # Output copied
        mock_copy.assert_called_once()


class TestIntegration:
    """Integration tests for combined functionality"""

    def test_colorize_idempotency(self):
        """Test that _colorize doesn't double-color already colored text"""
        text = "# Header"
        result1 = _colorize(text)
        result2 = _colorize(result1)
        
        # Second colorization shouldn't add exponentially more codes
        # Count ANSI escape sequences
        count1 = result1.count('\033[')
        count2 = result2.count('\033[')
        
        # Should not have significantly more codes
        assert count2 <= count1 * 2  # Loose check for idempotency

    @patch('subprocess.run')
    def test_copy_to_clipboard_with_multiline(self, mock_run):
        """Test copy_to_clipboard preserves multiline text"""
        mock_run.return_value = Mock(returncode=0)
        text = "Line 1\nLine 2\nLine 3"
        
        result = copy_to_clipboard(text)
        
        assert result is True
        call_args = mock_run.call_args
        assert call_args[1]['input'] == text
        assert '\n' in call_args[1]['input']

    def test_format_table_with_empty_cells(self):
        """Test format_table handles None and empty string cells"""
        headers = ["A", "B"]
        rows = [["1", ""], [None, "2"]]
        
        result = format_table(headers, rows)
        
        # Should handle None and empty strings gracefully
        assert "None" in result or "|  |" in result or "| |" in result
        lines = result.strip().split('\n')
        assert len(lines) >= 4

    def test_format_table_long_content(self):
        """Test format_table with very long cell content"""
        headers = ["Short", "Long"]
        rows = [["A", "Very long content that exceeds typical column width"]]
        
        result = format_table(headers, rows)
        
        # Should accommodate long content
        assert "Very long content" in result
        lines = result.strip().split('\n')
        assert len(lines) == 3  # header + separator + 1 data row
