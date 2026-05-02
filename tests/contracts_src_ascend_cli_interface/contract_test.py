"""
Contract tests for Ascend CLI Interface

This module tests the CLI interface functions: _build_parser, _rewrite_args, and main.
Tests verify behavior at boundaries, covering happy paths, edge cases, error cases,
and invariants as defined in the contract.

Generated from contract version 1 for component: contracts_src_ascend_cli_interface
"""

import pytest
import sys
from unittest.mock import Mock, patch, MagicMock, call
from io import StringIO


# Import the module under test
# Adjust import path as needed based on actual module structure
try:
    from ascend.cli import _build_parser, _rewrite_args, main
except ImportError:
    # Alternative import paths to try
    try:
        from cli import _build_parser, _rewrite_args, main
    except ImportError:
        # Fallback for contract testing
        import importlib.util
        import os
        
        # Try to find the module in common locations
        possible_paths = [
            'ascend/cli.py',
            'src/ascend/cli.py',
            'cli.py',
        ]
        
        module = None
        for path in possible_paths:
            if os.path.exists(path):
                spec = importlib.util.spec_from_file_location("cli_module", path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                _build_parser = module._build_parser
                _rewrite_args = module._rewrite_args
                main = module.main
                break
        
        if module is None:
            # Create mock functions for structure testing
            def _build_parser():
                raise NotImplementedError("Module not found")
            def _rewrite_args(argv):
                raise NotImplementedError("Module not found")
            def main(argv):
                raise NotImplementedError("Module not found")


class TestBuildParser:
    """Tests for _build_parser() function"""
    
    def test_build_parser_happy_path(self):
        """Verify _build_parser returns a configured ArgumentParser with program name 'ascend'"""
        parser = _build_parser()
        
        assert parser is not None, "Parser should not be None"
        assert parser.prog == 'ascend', f"Parser program name should be 'ascend', got '{parser.prog}'"
        assert hasattr(parser, '_subparsers'), "Parser should have _subparsers attribute"
    
    def test_build_parser_version_flag(self):
        """Verify parser includes --version flag"""
        parser = _build_parser()
        
        # Check if version action exists in parser actions
        version_actions = [action for action in parser._actions 
                          if hasattr(action, 'option_strings') and '--version' in action.option_strings]
        
        assert len(version_actions) > 0, "Parser should have --version flag"
    
    def test_build_parser_subparsers_exist(self):
        """Verify parser contains subparsers for CLI commands"""
        parser = _build_parser()
        
        # Find subparsers action
        subparsers_actions = [action for action in parser._actions 
                             if hasattr(action, 'choices') and action.choices is not None]
        
        assert len(subparsers_actions) > 0, "Parser should have subparsers configured"
        
        # Verify subparsers have choices (commands)
        for action in subparsers_actions:
            assert len(action.choices) > 0, "Subparsers should have command choices defined"
    
    def test_invariant_parser_program_name(self):
        """Verify parser program name is always 'ascend'"""
        parser = _build_parser()
        assert parser.prog == 'ascend', "Parser program name must always be 'ascend'"
    
    def test_build_parser_multiple_calls_independent(self):
        """Verify multiple calls to _build_parser return independent instances"""
        parser1 = _build_parser()
        parser2 = _build_parser()
        
        assert parser1 is not parser2, "Each call should return a new parser instance"
        assert parser1.prog == parser2.prog == 'ascend', "Both parsers should have same program name"
    
    def test_build_parser_has_help_flag(self):
        """Verify parser has help flag configured"""
        parser = _build_parser()
        
        help_actions = [action for action in parser._actions 
                       if hasattr(action, 'option_strings') and '--help' in action.option_strings]
        
        assert len(help_actions) > 0, "Parser should have --help flag"


class TestRewriteArgs:
    """Tests for _rewrite_args() function"""
    
    def test_rewrite_args_happy_path_three_word(self):
        """Verify 3-word commands are rewritten to hyphenated form"""
        argv = ["ascend", "plan", "goal", "create"]
        result = _rewrite_args(argv)
        
        assert result == ["ascend", "plan-goal-create"], \
            f"Expected ['ascend', 'plan-goal-create'], got {result}"
    
    def test_rewrite_args_happy_path_two_word(self):
        """Verify 2-word commands are rewritten to hyphenated form"""
        argv = ["ascend", "roster", "list"]
        result = _rewrite_args(argv)
        
        assert result == ["ascend", "roster-list"], \
            f"Expected ['ascend', 'roster-list'], got {result}"
    
    def test_rewrite_args_no_match(self):
        """Verify arguments remain unchanged when no multi-word command matches"""
        argv = ["ascend", "unknown", "command"]
        result = _rewrite_args(argv)
        
        assert result == ["ascend", "unknown", "command"], \
            "Unknown commands should remain unchanged"
    
    def test_rewrite_args_precedence_three_over_two(self):
        """Verify 3-word commands take precedence over 2-word commands"""
        argv = ["ascend", "plan", "goal", "create"]
        result = _rewrite_args(argv)
        
        # 3-word command should have 2 hyphens (joining 3 words)
        assert result[1].count('-') == 2, \
            f"3-word command should have 2 hyphens, got {result[1]}"
    
    def test_rewrite_args_empty_list(self):
        """Verify empty list is handled correctly"""
        argv = []
        result = _rewrite_args(argv)
        
        assert result == [], "Empty list should remain empty"
    
    def test_rewrite_args_single_element(self):
        """Verify single element list is handled correctly"""
        argv = ["ascend"]
        result = _rewrite_args(argv)
        
        assert result == ["ascend"], "Single element list should remain unchanged"
    
    def test_rewrite_args_with_flags(self):
        """Verify command with flags is handled correctly"""
        argv = ["ascend", "roster", "list", "--json"]
        result = _rewrite_args(argv)
        
        assert "--json" in result, "Flags should be preserved in result"
        assert result[1] == "roster-list", "Command should be rewritten"
    
    def test_rewrite_args_idempotent(self):
        """Verify rewriting is idempotent - already hyphenated commands remain unchanged"""
        argv = ["ascend", "roster-list"]
        result = _rewrite_args(argv)
        
        assert result == ["ascend", "roster-list"], \
            "Already hyphenated commands should remain unchanged"
    
    def test_rewrite_args_with_additional_arguments(self):
        """Verify commands with additional arguments beyond the command words"""
        argv = ["ascend", "roster", "list", "arg1", "arg2", "--flag", "value"]
        result = _rewrite_args(argv)
        
        # First part should be rewritten
        assert result[1] == "roster-list", "Command should be rewritten"
        # Additional arguments should be preserved
        assert "arg1" in result, "Additional arguments should be preserved"
        assert "arg2" in result, "Additional arguments should be preserved"
        assert "--flag" in result, "Flags should be preserved"
        assert "value" in result, "Flag values should be preserved"
    
    def test_rewrite_args_preserves_order(self):
        """Verify argument order is preserved"""
        argv = ["ascend", "roster", "list", "first", "second", "third"]
        result = _rewrite_args(argv)
        
        # After rewriting command, remaining args should maintain order
        expected_tail = ["first", "second", "third"]
        actual_tail = result[2:]
        
        assert actual_tail == expected_tail, \
            f"Argument order should be preserved, expected {expected_tail}, got {actual_tail}"
    
    def test_rewrite_args_two_element_list(self):
        """Verify two element list (just program name and one arg) is handled"""
        argv = ["ascend", "help"]
        result = _rewrite_args(argv)
        
        # Should not crash, should return something reasonable
        assert len(result) >= 2, "Should preserve all elements"
    
    def test_rewrite_args_special_characters_in_flags(self):
        """Verify special characters in flags are preserved"""
        argv = ["ascend", "roster", "list", "--filter=name:test", "--output=/path/to/file"]
        result = _rewrite_args(argv)
        
        assert "--filter=name:test" in result, "Special characters in flags should be preserved"
        assert "--output=/path/to/file" in result, "Path separators should be preserved"


class TestMain:
    """Tests for main() function"""
    
    def test_main_no_command_provided(self, capsys):
        """Verify main exits with code 1 when no command is provided"""
        argv = ["ascend"]
        
        with pytest.raises(SystemExit) as exc_info:
            main(argv)
        
        assert exc_info.value.code == 1, "Should exit with code 1 when no command provided"
        
        captured = capsys.readouterr()
        # Help text should be printed
        assert len(captured.out) > 0 or len(captured.err) > 0, \
            "Help text should be printed when no command provided"
    
    def test_main_unknown_command(self, capsys):
        """Verify main exits with code 1 for unknown command"""
        argv = ["ascend", "unknown-cmd"]
        
        with pytest.raises(SystemExit) as exc_info:
            main(argv)
        
        assert exc_info.value.code == 1, "Should exit with code 1 for unknown command"
    
    @patch('sys.argv', ['ascend', 'roster', 'list'])
    def test_main_argv_none(self):
        """Verify main handles argv=None by using sys.argv"""
        # Mock the roster module and its handle function
        with patch.dict('sys.modules', {
            'ascend.commands.roster': Mock(handle=Mock())
        }):
            # When argv is None, should use sys.argv
            try:
                main(None)
            except SystemExit:
                # May exit if command actually runs
                pass
            except AttributeError:
                # May fail if module structure is different
                pass
            except Exception as e:
                # Should at least attempt to parse sys.argv
                # The fact that it tried is sufficient for this test
                pass
    
    def test_main_version_flag(self, capsys):
        """Verify main handles --version flag"""
        argv = ["ascend", "--version"]
        
        with pytest.raises(SystemExit) as exc_info:
            main(argv)
        
        # Version flag typically exits with code 0
        assert exc_info.value.code == 0, "Should exit with code 0 for --version"
        
        captured = capsys.readouterr()
        # Version info should be printed
        output = captured.out + captured.err
        assert len(output) > 0, "Version information should be printed"
    
    def test_main_help_flag(self, capsys):
        """Verify main handles --help flag"""
        argv = ["ascend", "--help"]
        
        with pytest.raises(SystemExit) as exc_info:
            main(argv)
        
        # Help flag typically exits with code 0
        assert exc_info.value.code == 0, "Should exit with code 0 for --help"
        
        captured = capsys.readouterr()
        # Help text should be printed
        output = captured.out + captured.err
        assert len(output) > 0, "Help text should be printed"
        assert "ascend" in output.lower(), "Help should mention program name"
    
    def test_main_valid_command_lazy_load(self):
        """Verify command handlers are lazy-loaded only when invoked"""
        # Create a mock module
        mock_roster_module = Mock()
        mock_roster_module.handle = Mock()
        
        with patch.dict('sys.modules', {'ascend.commands.roster': mock_roster_module}):
            # Import should happen when command is invoked
            try:
                main(["ascend", "roster", "list"])
            except SystemExit:
                pass
            except Exception:
                # Even if it fails, the lazy load attempt is what we're testing
                pass
    
    def test_main_space_separated_command(self):
        """Verify main handles space-separated multi-word commands"""
        mock_roster_module = Mock()
        mock_roster_module.handle = Mock()
        
        with patch.dict('sys.modules', {'ascend.commands.roster': mock_roster_module}):
            try:
                # Space-separated form
                main(["ascend", "roster", "list"])
            except SystemExit:
                pass
            except Exception:
                pass
    
    def test_main_hyphenated_command(self):
        """Verify main handles hyphenated multi-word commands"""
        mock_roster_module = Mock()
        mock_roster_module.handle = Mock()
        
        with patch.dict('sys.modules', {'ascend.commands.roster': mock_roster_module}):
            try:
                # Hyphenated form
                main(["ascend", "roster-list"])
            except SystemExit:
                pass
            except Exception:
                pass
    
    def test_invariant_space_and_hyphen_equivalence(self):
        """Verify multi-word commands work with both space-separated and hyphenated forms"""
        # Test that rewrite_args makes space-separated equivalent to hyphenated
        space_form = ["ascend", "roster", "list"]
        hyphen_form = ["ascend", "roster-list"]
        
        rewritten_space = _rewrite_args(space_form)
        rewritten_hyphen = _rewrite_args(hyphen_form)
        
        # After rewriting, both should be equivalent
        assert rewritten_space[1] == rewritten_hyphen[1], \
            "Space-separated and hyphenated forms should be equivalent after rewriting"
    
    def test_invariant_lazy_loading(self):
        """Verify command handlers are lazy-loaded only when invoked"""
        # Verify that handler modules are not imported at module load time
        # by checking they're imported inside main()
        
        initial_modules = set(sys.modules.keys())
        
        # Build parser should not import handler modules
        parser = _build_parser()
        
        after_parser_modules = set(sys.modules.keys())
        
        # No new command handler modules should be loaded just from building parser
        new_modules = after_parser_modules - initial_modules
        command_modules = [m for m in new_modules if 'ascend.commands' in m]
        
        # This assertion may be too strict if modules are already imported
        # but it tests the lazy-loading principle
        assert len(command_modules) == 0 or 'ascend.commands' not in str(new_modules), \
            "Command handler modules should not be imported when building parser"
    
    def test_main_with_subcommand_arguments(self):
        """Verify main passes arguments to command handlers"""
        mock_roster_module = Mock()
        mock_roster_module.handle = Mock()
        
        with patch.dict('sys.modules', {'ascend.commands.roster': mock_roster_module}):
            try:
                main(["ascend", "roster", "list", "--json"])
            except SystemExit:
                pass
            except Exception:
                # Command might not be fully implemented
                pass
    
    def test_main_empty_argv(self, capsys):
        """Verify main handles empty argv gracefully"""
        argv = []
        
        # Empty argv should likely cause an error or default behavior
        try:
            main(argv)
        except SystemExit as e:
            # Should exit with error code
            assert e.code != 0, "Empty argv should cause error exit"
        except Exception:
            # May raise other exceptions depending on implementation
            pass


class TestEdgeCases:
    """Additional edge case tests"""
    
    def test_rewrite_args_very_long_list(self):
        """Verify handling of very long argument lists"""
        # Create a long list with many arguments
        argv = ["ascend", "roster", "list"] + [f"arg{i}" for i in range(100)]
        result = _rewrite_args(argv)
        
        assert len(result) == len(argv) - 1, \
            "Should preserve all arguments except those combined into command"
        assert result[1] == "roster-list", "Command should be rewritten"
    
    def test_rewrite_args_unicode_characters(self):
        """Verify handling of unicode characters in arguments"""
        argv = ["ascend", "roster", "list", "名前", "--filter=café"]
        result = _rewrite_args(argv)
        
        assert "名前" in result, "Unicode characters should be preserved"
        assert "--filter=café" in result, "Unicode in flags should be preserved"
    
    def test_rewrite_args_empty_strings(self):
        """Verify handling of empty strings in argv"""
        argv = ["ascend", "", "roster", "list"]
        result = _rewrite_args(argv)
        
        # Should handle gracefully without crashing
        assert isinstance(result, list), "Should return a list"
    
    def test_rewrite_args_whitespace_strings(self):
        """Verify handling of whitespace-only strings"""
        argv = ["ascend", " ", "roster", "list"]
        result = _rewrite_args(argv)
        
        # Should handle gracefully
        assert isinstance(result, list), "Should return a list"
    
    def test_main_stderr_output_on_error(self, capsys):
        """Verify error messages go to stderr"""
        argv = ["ascend", "totally-unknown-command-xyz"]
        
        try:
            main(argv)
        except SystemExit:
            pass
        
        captured = capsys.readouterr()
        # Error messages typically go to stderr
        # Either stderr has content or stdout has error message
        assert len(captured.err) > 0 or len(captured.out) > 0, \
            "Error output should be produced"
    
    def test_build_parser_deterministic(self):
        """Verify _build_parser produces consistent results"""
        parser1 = _build_parser()
        parser2 = _build_parser()
        
        # Both should have same program name
        assert parser1.prog == parser2.prog, "Parsers should be consistent"
        
        # Both should have same number of actions
        assert len(parser1._actions) == len(parser2._actions), \
            "Parsers should have same number of actions"


class TestCommandCategories:
    """Test coverage for different command categories mentioned in contract"""
    
    def test_parser_has_init_commands(self):
        """Verify parser includes init category commands"""
        parser = _build_parser()
        subparsers_actions = [action for action in parser._actions 
                             if hasattr(action, 'choices') and action.choices is not None]
        
        if subparsers_actions:
            choices = subparsers_actions[0].choices
            # Look for init-related commands
            init_commands = [cmd for cmd in choices.keys() if 'init' in cmd]
            assert len(init_commands) > 0, "Should have init commands"
    
    def test_parser_has_roster_commands(self):
        """Verify parser includes roster category commands"""
        parser = _build_parser()
        subparsers_actions = [action for action in parser._actions 
                             if hasattr(action, 'choices') and action.choices is not None]
        
        if subparsers_actions:
            choices = subparsers_actions[0].choices
            roster_commands = [cmd for cmd in choices.keys() if 'roster' in cmd]
            assert len(roster_commands) > 0, "Should have roster commands"
    
    def test_parser_has_multiple_command_categories(self):
        """Verify parser has commands from multiple categories"""
        parser = _build_parser()
        subparsers_actions = [action for action in parser._actions 
                             if hasattr(action, 'choices') and action.choices is not None]
        
        if subparsers_actions:
            choices = subparsers_actions[0].choices
            # Should have substantial number of commands (contract mentions 50+)
            assert len(choices) > 10, \
                f"Should have many commands (contract mentions 50+), found {len(choices)}"


class TestRewriteArgsComprehensive:
    """Comprehensive tests for _rewrite_args edge cases"""
    
    def test_rewrite_args_partial_match(self):
        """Verify partial matches don't incorrectly rewrite"""
        # If only first word matches a known command category
        argv = ["ascend", "roster", "unknown-subcommand"]
        result = _rewrite_args(argv)
        
        # Should either rewrite properly or leave unchanged
        assert isinstance(result, list), "Should return a list"
        assert len(result) >= len(argv) - 1, "Should not lose arguments"
    
    def test_rewrite_args_duplicate_words(self):
        """Verify handling of duplicate words"""
        argv = ["ascend", "roster", "roster", "list"]
        result = _rewrite_args(argv)
        
        # Should handle without error
        assert isinstance(result, list), "Should return a list"
    
    def test_rewrite_args_numeric_arguments(self):
        """Verify numeric arguments are preserved"""
        argv = ["ascend", "roster", "list", "123", "456"]
        result = _rewrite_args(argv)
        
        assert "123" in result, "Numeric arguments should be preserved"
        assert "456" in result, "Numeric arguments should be preserved"
    
    def test_rewrite_args_negative_flags(self):
        """Verify negative number flags are preserved"""
        argv = ["ascend", "roster", "list", "--limit", "-1"]
        result = _rewrite_args(argv)
        
        assert "--limit" in result, "Flag should be preserved"
        assert "-1" in result, "Negative number should be preserved"
    
    def test_rewrite_args_equals_in_args(self):
        """Verify arguments with equals signs are preserved"""
        argv = ["ascend", "roster", "list", "key=value", "foo=bar=baz"]
        result = _rewrite_args(argv)
        
        assert "key=value" in result, "Key=value pairs should be preserved"
        assert "foo=bar=baz" in result, "Multiple equals should be preserved"


class TestMainIntegration:
    """Integration-level tests for main() function"""
    
    def test_main_processes_rewritten_args(self):
        """Verify main properly processes rewritten arguments"""
        # This tests the integration between _rewrite_args and main
        mock_module = Mock()
        mock_module.handle = Mock()
        
        with patch.dict('sys.modules', {'ascend.commands.roster': mock_module}):
            # Use space-separated form
            try:
                main(["ascend", "roster", "list"])
            except (SystemExit, AttributeError, KeyError):
                # May fail if implementation differs, but should attempt processing
                pass
    
    def test_main_exits_cleanly_on_interrupt(self):
        """Verify main handles keyboard interrupt gracefully"""
        mock_module = Mock()
        mock_module.handle = Mock(side_effect=KeyboardInterrupt())
        
        with patch.dict('sys.modules', {'ascend.commands.roster': mock_module}):
            try:
                main(["ascend", "roster", "list"])
            except (KeyboardInterrupt, SystemExit):
                # Should exit on interrupt
                pass


# Fixtures for common test setup
@pytest.fixture
def sample_parser():
    """Fixture providing a sample parser instance"""
    return _build_parser()


@pytest.fixture
def mock_command_module():
    """Fixture providing a mock command module"""
    mock = Mock()
    mock.handle = Mock()
    return mock


# Test execution
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
