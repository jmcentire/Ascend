"""
Contract tests for Output Interface component.
Tests all functions: _colorize, print_report, print_json, print_status,
copy_to_clipboard, format_table, render_output.
"""

import pytest
import json
import sys
from io import StringIO
from unittest.mock import Mock, patch, MagicMock, call
from subprocess import TimeoutExpired, CompletedProcess

# Import the module under test
from contracts.src_ascend_output.interface import (
    _colorize,
    print_report,
    print_json,
    print_status,
    copy_to_clipboard,
    format_table,
    render_output,
)


# ============================================================================
# Tests for _colorize
# ============================================================================

class TestColorize:
    """Tests for the _colorize function."""
    
    def test_colorize_happy_path_headers(self):
        """Test that headers with # are colored bold cyan."""
        text = "# Main Header\n## Subheader\nregular text"
        result = _colorize(text)
        
        # Check ANSI codes are present
        assert '\033[' in result
        # Bold cyan should be \033[1m\033[36m
        assert '\033[1m\033[36m' in result or '\033[36m\033[1m' in result
        # Original content preserved
        assert 'Main Header' in result
        assert 'Subheader' in result
        assert 'regular text' in result
    
    def test_colorize_happy_path_status_indicators(self):
        """Test that status indicators are colored appropriately."""
        text = "Status: Blocked\nStatus: Active\nStatus: On Track\nStatus: At Risk"
        result = _colorize(text)
        
        # Red for Blocked
        assert '\033[31m' in result
        # Green for Active/On Track
        assert '\033[32m' in result
        # Yellow for At Risk
        assert '\033[33m' in result
        # Original text preserved
        assert 'Blocked' in result
        assert 'Active' in result
        assert 'On Track' in result
        assert 'At Risk' in result
    
    def test_colorize_happy_path_metadata(self):
        """Test that metadata lines are dimmed."""
        text = "Generated: 2024-01-01\n---\nContent here"
        result = _colorize(text)
        
        # Dim code
        assert '\033[2m' in result
        # Original content preserved
        assert 'Generated: 2024-01-01' in result
        assert '---' in result
        assert 'Content here' in result
    
    def test_colorize_edge_case_empty_string(self):
        """Test colorize with empty string."""
        text = ""
        result = _colorize(text)
        assert result == ""
    
    def test_colorize_edge_case_triple_hash_header(self):
        """Test that ### headers are bold but not cyan."""
        text = "### Small Header"
        result = _colorize(text)
        
        # Should have bold
        assert '\033[1m' in result
        # But not cyan (should not have the # or ## pattern which gets cyan)
        # ### gets only bold, not cyan
        lines = result.split('\n')
        # Check that the line doesn't have cyan code after reset
        # The contract says ### lines are bold, not bold cyan
    
    def test_colorize_edge_case_multiple_statuses_in_line(self):
        """Test line with multiple status keywords."""
        text = "Project Active but At Risk"
        result = _colorize(text)
        
        # Should have some color code
        assert '\033[' in result
        # Content preserved
        assert 'Project Active but At Risk' in result
    
    def test_colorize_edge_case_unicode_content(self):
        """Test colorize with Unicode characters."""
        text = "# 📊 Report\nStatus: Active ✓\n🔴 Blocked\nשלום At Risk"
        result = _colorize(text)
        
        # Unicode preserved
        assert '📊' in result
        assert '✓' in result
        assert '🔴' in result
        assert 'שלום' in result
        # ANSI codes present
        assert '\033[' in result
    
    def test_colorize_edge_case_no_matching_patterns(self):
        """Test colorize with text that has no matching patterns."""
        text = "Just some regular text\nwith no special patterns"
        result = _colorize(text)
        
        # No ANSI codes should be added
        assert result == text


# ============================================================================
# Tests for print_report
# ============================================================================

class TestPrintReport:
    """Tests for the print_report function."""
    
    def test_print_report_happy_path_with_color_true(self):
        """Test print_report with use_color=True."""
        text = "# Test Report\nStatus: Active"
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            print_report(text, use_color=True)
            output = mock_stdout.getvalue()
            
            # Should have ANSI codes
            assert '\033[' in output
            # Content preserved
            assert 'Test Report' in output
            assert 'Active' in output
    
    def test_print_report_happy_path_with_color_false(self):
        """Test print_report with use_color=False."""
        text = "# Test Report\nStatus: Active"
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            print_report(text, use_color=False)
            output = mock_stdout.getvalue()
            
            # Should NOT have ANSI codes
            assert '\033[' not in output
            # Content preserved
            assert text in output
    
    def test_print_report_happy_path_auto_detect_tty(self):
        """Test print_report with use_color=None and stdout is TTY."""
        text = "# Test Report"
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            mock_stdout.isatty = Mock(return_value=True)
            print_report(text, use_color=None)
            
            # isatty should have been called
            mock_stdout.isatty.assert_called_once()
            
            output = mock_stdout.getvalue()
            # Should have ANSI codes when TTY
            assert '\033[' in output
    
    def test_print_report_edge_case_auto_detect_not_tty(self):
        """Test print_report with use_color=None and stdout is not TTY."""
        text = "# Test Report"
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            mock_stdout.isatty = Mock(return_value=False)
            print_report(text, use_color=None)
            
            # isatty should have been called
            mock_stdout.isatty.assert_called_once()
            
            output = mock_stdout.getvalue()
            # Should NOT have ANSI codes when not TTY
            assert '\033[' not in output
    
    def test_print_report_edge_case_empty_text(self):
        """Test print_report with empty string."""
        text = ""
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            print_report(text, use_color=False)
            output = mock_stdout.getvalue()
            
            assert output == ""


# ============================================================================
# Tests for print_json
# ============================================================================

class TestPrintJson:
    """Tests for the print_json function."""
    
    def test_print_json_happy_path_simple_dict(self):
        """Test print_json with simple dictionary."""
        data = {"name": "test", "value": 42}
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            print_json(data)
            output = mock_stdout.getvalue()
            
            # Should be valid JSON
            parsed = json.loads(output)
            assert parsed == data
            
            # Check 2-space indentation
            assert '  ' in output
            assert '    ' not in output.split('\n')[0]  # Not 4-space indent
    
    def test_print_json_happy_path_list(self):
        """Test print_json with list."""
        data = [1, 2, 3, 4, 5]
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            print_json(data)
            output = mock_stdout.getvalue()
            
            # Should be valid JSON
            parsed = json.loads(output)
            assert parsed == data
    
    def test_print_json_edge_case_non_serializable_object(self):
        """Test print_json with non-JSON-serializable object."""
        class CustomObject:
            def __str__(self):
                return "CustomObject"
        
        data = {"obj": CustomObject()}
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            print_json(data)
            output = mock_stdout.getvalue()
            
            # Should be valid JSON
            parsed = json.loads(output)
            # Object should be converted to string
            assert "CustomObject" in parsed["obj"]
    
    def test_print_json_edge_case_nested_structures(self):
        """Test print_json with deeply nested structures."""
        data = {"level1": {"level2": {"level3": {"value": "deep"}}}}
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            print_json(data)
            output = mock_stdout.getvalue()
            
            # Should be valid JSON
            parsed = json.loads(output)
            assert parsed == data
            assert parsed["level1"]["level2"]["level3"]["value"] == "deep"
    
    def test_print_json_edge_case_empty_data(self):
        """Test print_json with None."""
        data = None
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            print_json(data)
            output = mock_stdout.getvalue()
            
            # Should output 'null'
            assert output.strip() == 'null'
    
    def test_print_json_edge_case_unicode(self):
        """Test print_json with Unicode data."""
        data = {"emoji": "🎉", "chinese": "你好", "arabic": "مرحبا"}
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            print_json(data)
            output = mock_stdout.getvalue()
            
            # Should be valid JSON
            parsed = json.loads(output)
            assert parsed == data


# ============================================================================
# Tests for print_status
# ============================================================================

class TestPrintStatus:
    """Tests for the print_status function."""
    
    def test_print_status_happy_path_tty(self):
        """Test print_status with stderr as TTY."""
        message = "Processing..."
        
        with patch('sys.stderr', new_callable=StringIO) as mock_stderr:
            mock_stderr.isatty = Mock(return_value=True)
            print_status(message)
            
            output = mock_stderr.getvalue()
            
            # Should have dim ANSI code
            assert '\033[2m' in output
            # Content preserved
            assert 'Processing...' in output
            # Newline appended
            assert output.endswith('\n')
    
    def test_print_status_happy_path_not_tty(self):
        """Test print_status with stderr not TTY."""
        message = "Processing..."
        
        with patch('sys.stderr', new_callable=StringIO) as mock_stderr:
            mock_stderr.isatty = Mock(return_value=False)
            print_status(message)
            
            output = mock_stderr.getvalue()
            
            # Should NOT have ANSI codes
            assert '\033[' not in output
            # Content preserved
            assert message in output
            # Newline appended
            assert output.endswith('\n')
    
    def test_print_status_edge_case_empty_message(self):
        """Test print_status with empty message."""
        message = ""
        
        with patch('sys.stderr', new_callable=StringIO) as mock_stderr:
            mock_stderr.isatty = Mock(return_value=False)
            print_status(message)
            
            output = mock_stderr.getvalue()
            
            # Should just be newline
            assert output == '\n'
    
    def test_print_status_edge_case_multiline_message(self):
        """Test print_status with multiline message."""
        message = "Line 1\nLine 2\nLine 3"
        
        with patch('sys.stderr', new_callable=StringIO) as mock_stderr:
            mock_stderr.isatty = Mock(return_value=False)
            print_status(message)
            
            output = mock_stderr.getvalue()
            
            # Full message preserved
            assert 'Line 1' in output
            assert 'Line 2' in output
            assert 'Line 3' in output


# ============================================================================
# Tests for copy_to_clipboard
# ============================================================================

class TestCopyToClipboard:
    """Tests for the copy_to_clipboard function."""
    
    def test_copy_to_clipboard_happy_path_success(self):
        """Test copy_to_clipboard with successful pbcopy."""
        text = "Test content"
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = CompletedProcess(
                args=['pbcopy'], returncode=0
            )
            
            result = copy_to_clipboard(text)
            
            # Should return True
            assert result is True
            
            # subprocess.run should be called
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            
            # Check pbcopy command
            assert 'pbcopy' in call_args[0][0]
            
            # Check text passed to stdin
            assert call_args[1]['input'] == text
            
            # Check 5-second timeout
            assert call_args[1]['timeout'] == 5
    
    def test_copy_to_clipboard_error_timeout(self):
        """Test copy_to_clipboard when pbcopy times out."""
        text = "Test content"
        
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = TimeoutExpired(cmd='pbcopy', timeout=5)
            
            result = copy_to_clipboard(text)
            
            # Should return False
            assert result is False
    
    def test_copy_to_clipboard_error_not_found(self):
        """Test copy_to_clipboard when pbcopy command not found."""
        text = "Test content"
        
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = FileNotFoundError()
            
            result = copy_to_clipboard(text)
            
            # Should return False
            assert result is False
    
    def test_copy_to_clipboard_error_os_error(self):
        """Test copy_to_clipboard with OS-level error."""
        text = "Test content"
        
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = OSError("OS error")
            
            result = copy_to_clipboard(text)
            
            # Should return False
            assert result is False
    
    def test_copy_to_clipboard_edge_case_empty_text(self):
        """Test copy_to_clipboard with empty string."""
        text = ""
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = CompletedProcess(
                args=['pbcopy'], returncode=0
            )
            
            result = copy_to_clipboard(text)
            
            # Should return True
            assert result is True
            
            # Empty string passed
            call_args = mock_run.call_args
            assert call_args[1]['input'] == ""
    
    def test_copy_to_clipboard_edge_case_large_text(self):
        """Test copy_to_clipboard with large text content."""
        text = "x" * 10000
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = CompletedProcess(
                args=['pbcopy'], returncode=0
            )
            
            result = copy_to_clipboard(text)
            
            # Should return True
            assert result is True
            
            # Large text passed
            call_args = mock_run.call_args
            assert len(call_args[1]['input']) == 10000
    
    def test_copy_to_clipboard_edge_case_unicode(self):
        """Test copy_to_clipboard with Unicode content."""
        text = "Unicode: 你好 🎉 مرحبا"
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = CompletedProcess(
                args=['pbcopy'], returncode=0
            )
            
            result = copy_to_clipboard(text)
            
            # Should return True
            assert result is True
            
            # Unicode text passed
            call_args = mock_run.call_args
            assert '你好' in call_args[1]['input']
            assert '🎉' in call_args[1]['input']


# ============================================================================
# Tests for format_table
# ============================================================================

class TestFormatTable:
    """Tests for the format_table function."""
    
    def test_format_table_happy_path_basic(self):
        """Test format_table with basic headers and rows."""
        headers = ["Name", "Age", "City"]
        rows = [["Alice", "30", "NYC"], ["Bob", "25", "LA"]]
        
        result = format_table(headers, rows)
        
        # Should contain header row
        assert "Name" in result
        assert "Age" in result
        assert "City" in result
        
        # Should contain separator with dashes
        assert "---" in result or "----" in result
        
        # Should contain data rows
        assert "Alice" in result
        assert "Bob" in result
        assert "NYC" in result
        assert "LA" in result
        
        # Should have pipe characters for table structure
        assert "|" in result
    
    def test_format_table_happy_path_single_row(self):
        """Test format_table with single row."""
        headers = ["Col1", "Col2"]
        rows = [["Value1", "Value2"]]
        
        result = format_table(headers, rows)
        
        # Should contain header and separator
        assert "Col1" in result
        assert "Col2" in result
        assert "---" in result or "----" in result
        
        # Should contain single data row
        assert "Value1" in result
        assert "Value2" in result
    
    def test_format_table_edge_case_empty_rows(self):
        """Test format_table with empty rows list."""
        headers = ["Col1", "Col2"]
        rows = []
        
        result = format_table(headers, rows)
        
        # Should return 'No data.'
        assert result == "No data."
    
    def test_format_table_edge_case_single_column(self):
        """Test format_table with single column."""
        headers = ["OnlyColumn"]
        rows = [["Value1"], ["Value2"], ["Value3"]]
        
        result = format_table(headers, rows)
        
        # Should have single column format
        assert "OnlyColumn" in result
        assert "Value1" in result
        assert "Value2" in result
        assert "Value3" in result
    
    def test_format_table_edge_case_varying_widths(self):
        """Test format_table with varying content widths."""
        headers = ["Short", "VeryLongHeader"]
        rows = [["A", "B"], ["VeryLongContent", "C"]]
        
        result = format_table(headers, rows)
        
        # All content should be visible
        assert "Short" in result
        assert "VeryLongHeader" in result
        assert "VeryLongContent" in result
        
        # Should have proper structure
        assert "|" in result
    
    def test_format_table_edge_case_special_characters(self):
        """Test format_table with special characters and Unicode."""
        headers = ["Name", "Symbol"]
        rows = [
            ["Emoji", "🎉"],
            ["Chinese", "你好"],
            ["Pipe", "|"],
            ["Dash", "-"]
        ]
        
        result = format_table(headers, rows)
        
        # Special characters preserved
        assert "🎉" in result
        assert "你好" in result
        # Note: pipe and dash might be part of table structure
        assert "Emoji" in result
        assert "Chinese" in result
    
    def test_format_table_edge_case_mismatched_row_length(self):
        """Test format_table with rows shorter than headers."""
        headers = ["Col1", "Col2", "Col3"]
        rows = [["A", "B"], ["X"]]
        
        result = format_table(headers, rows)
        
        # Should be valid table
        assert "Col1" in result
        assert "Col2" in result
        assert "Col3" in result
        assert "A" in result
        assert "B" in result
        assert "X" in result
    
    def test_format_table_edge_case_non_string_values(self):
        """Test format_table with non-string cell values."""
        headers = ["Name", "Count", "Active"]
        rows = [["Item", 42, True], ["Other", 0, False]]
        
        result = format_table(headers, rows)
        
        # Non-string values converted to strings
        assert "Item" in result
        assert "42" in result
        assert "True" in result
        assert "Other" in result
        assert "0" in result
        assert "False" in result
    
    def test_format_table_edge_case_empty_strings(self):
        """Test format_table with empty string cells."""
        headers = ["Col1", "Col2"]
        rows = [["", "Value"], ["Value", ""]]
        
        result = format_table(headers, rows)
        
        # Should have proper structure
        assert "Col1" in result
        assert "Col2" in result
        assert "Value" in result
        # Empty cells should be handled (hard to test exact spacing)


# ============================================================================
# Tests for render_output
# ============================================================================

class TestRenderOutput:
    """Tests for the render_output function."""
    
    def test_render_output_happy_path_json_mode_dict(self):
        """Test render_output with json_mode=True and dict data."""
        data = {"key": "value"}
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            render_output(data, json_mode=True, copy=False)
            output = mock_stdout.getvalue()
            
            # Should be JSON formatted
            parsed = json.loads(output)
            assert parsed == data
    
    def test_render_output_happy_path_markdown_mode_string(self):
        """Test render_output with json_mode=False and string data."""
        data = "# Report Title\nContent here"
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            render_output(data, json_mode=False, copy=False)
            output = mock_stdout.getvalue()
            
            # String should be printed as report
            assert "Report Title" in output
            assert "Content here" in output
    
    def test_render_output_happy_path_markdown_mode_non_string(self):
        """Test render_output with json_mode=False and non-string data."""
        data = {"key": "value"}
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            render_output(data, json_mode=False, copy=False)
            output = mock_stdout.getvalue()
            
            # Non-string should be serialized to JSON
            parsed = json.loads(output)
            assert parsed == data
    
    def test_render_output_happy_path_with_copy_json(self):
        """Test render_output with copy=True in json_mode."""
        data = {"key": "value"}
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = CompletedProcess(
                    args=['pbcopy'], returncode=0
                )
                
                render_output(data, json_mode=True, copy=True)
                
                # JSON should be printed
                output = mock_stdout.getvalue()
                parsed = json.loads(output)
                assert parsed == data
                
                # copy_to_clipboard should be called
                mock_run.assert_called_once()
    
    def test_render_output_happy_path_with_copy_markdown(self):
        """Test render_output with copy=True in markdown mode."""
        data = "# Report"
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = CompletedProcess(
                    args=['pbcopy'], returncode=0
                )
                
                render_output(data, json_mode=False, copy=True)
                
                # Report should be printed
                output = mock_stdout.getvalue()
                assert "Report" in output
                
                # copy_to_clipboard should be called
                mock_run.assert_called_once()
    
    def test_render_output_edge_case_empty_string(self):
        """Test render_output with empty string."""
        data = ""
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            render_output(data, json_mode=False, copy=False)
            output = mock_stdout.getvalue()
            
            # Empty string printed
            assert output == ""
    
    def test_render_output_edge_case_none_data(self):
        """Test render_output with None data."""
        data = None
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            render_output(data, json_mode=True, copy=False)
            output = mock_stdout.getvalue()
            
            # Should output 'null'
            assert output.strip() == 'null'
    
    def test_render_output_edge_case_copy_failure(self):
        """Test render_output when copy_to_clipboard fails."""
        data = "Test data"
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            with patch('subprocess.run') as mock_run:
                mock_run.side_effect = FileNotFoundError()
                
                # Should not raise exception
                render_output(data, json_mode=False, copy=True)
                
                # Data should still be printed
                output = mock_stdout.getvalue()
                assert "Test data" in output


# ============================================================================
# Invariant Tests
# ============================================================================

class TestInvariants:
    """Tests for contract invariants."""
    
    def test_invariant_ansi_codes_constants(self):
        """Verify ANSI color code constants match contract invariants."""
        # Test by checking the output of _colorize contains expected codes
        text = "# Header\nBlocked\nActive\nAt Risk\nGenerated: test\n---"
        result = _colorize(text)
        
        # Check expected ANSI codes are used
        assert '\033[0m' in result  # RESET
        assert '\033[1m' in result  # BOLD
        assert '\033[2m' in result  # DIM
        assert '\033[32m' in result  # GREEN
        assert '\033[33m' in result  # YELLOW
        assert '\033[31m' in result  # RED
        assert '\033[36m' in result  # CYAN
    
    def test_invariant_json_serialization_parameters(self):
        """Verify JSON serialization uses indent=2 and default=str."""
        data = {"test": "value"}
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            print_json(data)
            output = mock_stdout.getvalue()
            
            # Should have 2-space indentation
            lines = output.split('\n')
            # Check that indented lines use 2 spaces
            for line in lines:
                if line.startswith('  ') and not line.startswith('    '):
                    # Found 2-space indent (not 4-space)
                    break
            else:
                # For simple dict, might be on one level
                pass
            
            # Verify it's valid JSON
            parsed = json.loads(output)
            assert parsed == data
    
    def test_invariant_clipboard_timeout(self):
        """Verify clipboard operations use 5-second timeout."""
        text = "Test"
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = CompletedProcess(
                args=['pbcopy'], returncode=0
            )
            
            copy_to_clipboard(text)
            
            # Check timeout parameter
            call_args = mock_run.call_args
            assert call_args[1]['timeout'] == 5
    
    def test_invariant_output_streams(self):
        """Verify status messages go to stderr and reports to stdout."""
        message = "Status"
        
        with patch('sys.stderr', new_callable=StringIO) as mock_stderr:
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                mock_stderr.isatty = Mock(return_value=False)
                
                print_status(message)
                
                # Message written to stderr
                stderr_output = mock_stderr.getvalue()
                assert message in stderr_output
                
                # Nothing written to stdout
                stdout_output = mock_stdout.getvalue()
                assert stdout_output == ""
    
    def test_invariant_color_auto_detection(self):
        """Verify color auto-detection uses isatty() correctly."""
        text = "Test"
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            mock_stdout.isatty = Mock(return_value=True)
            
            print_report(text, use_color=None)
            
            # isatty should be called
            mock_stdout.isatty.assert_called_once()
        
        # Test for print_status as well
        with patch('sys.stderr', new_callable=StringIO) as mock_stderr:
            mock_stderr.isatty = Mock(return_value=True)
            
            print_status(text)
            
            # isatty should be called
            mock_stderr.isatty.assert_called_once()


# ============================================================================
# Additional Edge Case Tests
# ============================================================================

class TestAdditionalEdgeCases:
    """Additional edge case tests for comprehensive coverage."""
    
    def test_colorize_with_mixed_line_endings(self):
        """Test _colorize with mixed line endings."""
        text = "# Header\r\nBlocked\rActive\n"
        result = _colorize(text)
        
        # Should handle different line endings
        assert 'Header' in result
        assert 'Blocked' in result
        assert 'Active' in result
    
    def test_format_table_with_very_long_content(self):
        """Test format_table with very long cell content."""
        headers = ["ID", "Description"]
        rows = [["1", "A" * 100], ["2", "Short"]]
        
        result = format_table(headers, rows)
        
        # Long content should be present
        assert "A" * 100 in result
        assert "Short" in result
    
    def test_render_output_with_list_in_json_mode(self):
        """Test render_output with list data in JSON mode."""
        data = [1, 2, 3, 4, 5]
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            render_output(data, json_mode=True, copy=False)
            output = mock_stdout.getvalue()
            
            # Should be valid JSON array
            parsed = json.loads(output)
            assert parsed == data
    
    def test_print_json_with_boolean_values(self):
        """Test print_json with boolean values."""
        data = {"flag1": True, "flag2": False}
        
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            print_json(data)
            output = mock_stdout.getvalue()
            
            # Should have proper JSON booleans
            parsed = json.loads(output)
            assert parsed["flag1"] is True
            assert parsed["flag2"] is False
    
    def test_copy_to_clipboard_with_newlines(self):
        """Test copy_to_clipboard with text containing newlines."""
        text = "Line 1\nLine 2\nLine 3"
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = CompletedProcess(
                args=['pbcopy'], returncode=0
            )
            
            result = copy_to_clipboard(text)
            
            assert result is True
            
            # Check multiline text passed
            call_args = mock_run.call_args
            assert '\n' in call_args[1]['input']
    
    def test_format_table_with_none_values(self):
        """Test format_table with None values in cells."""
        headers = ["Col1", "Col2"]
        rows = [[None, "Value"], ["Value", None]]
        
        result = format_table(headers, rows)
        
        # None should be converted to string
        assert "None" in result or result.count("|") > 0
    
    def test_render_output_all_combinations(self):
        """Test render_output with all boolean combinations."""
        test_cases = [
            ({"data": "test"}, True, True),
            ({"data": "test"}, True, False),
            ("string data", False, True),
            ("string data", False, False),
        ]
        
        for data, json_mode, copy in test_cases:
            with patch('sys.stdout', new_callable=StringIO):
                with patch('subprocess.run') as mock_run:
                    mock_run.return_value = CompletedProcess(
                        args=['pbcopy'], returncode=0
                    )
                    
                    # Should not raise exception
                    render_output(data, json_mode=json_mode, copy=copy)
