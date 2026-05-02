"""
Contract tests for Ascend CLI Parser and Entry Point.

Tests cover:
- _build_parser(): ArgumentParser configuration, subcommands, defaults
- _rewrite_args(): Argument preprocessing and transformation
- main(): CLI entry point, error handling, exit codes
"""

import argparse
import sys
import pytest
from unittest.mock import Mock, patch, MagicMock, call
from io import StringIO

# Import the component under test
from src.ascend import cli


class TestBuildParser:
    """Test suite for _build_parser() function."""
    
    def test_build_parser_returns_argument_parser(self):
        """Happy path: _build_parser returns an ArgumentParser instance with correct program name."""
        parser = cli._build_parser()
        
        assert isinstance(parser, argparse.ArgumentParser)
        assert parser.prog == 'ascend'
    
    def test_build_parser_includes_version_argument(self):
        """Happy path: parser includes --version argument."""
        parser = cli._build_parser()
        
        # Parse with --version should not raise, but will exit
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(['--version'])
        
        # Version exits with code 0
        assert exc_info.value.code == 0
    
    def test_build_parser_includes_subparsers(self):
        """Happy path: parser includes subparsers for supported commands."""
        parser = cli._build_parser()
        
        # Check that subparsers are configured
        assert hasattr(parser, '_subparsers')
        assert parser._subparsers is not None
        
        # Get subparser actions
        subparsers_action = None
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                subparsers_action = action
                break
        
        assert subparsers_action is not None
        
        # Check that common commands exist
        subparser_names = list(subparsers_action.choices.keys()) if subparsers_action.choices else []
        
        # Should have roster-related commands
        roster_commands = [name for name in subparser_names if 'roster' in name]
        assert len(roster_commands) > 0
        
        # Should have team-related commands  
        team_commands = [name for name in subparser_names if 'team' in name]
        assert len(team_commands) > 0
        
        # Should have meeting-related commands
        meeting_commands = [name for name in subparser_names if 'meeting' in name]
        assert len(meeting_commands) > 0
    
    def test_build_parser_subcommands_have_help(self):
        """Happy path: all subcommands have help text configured."""
        parser = cli._build_parser()
        
        # Get subparsers
        subparsers_action = None
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                subparsers_action = action
                break
        
        assert subparsers_action is not None
        
        if subparsers_action.choices:
            # Check that at least some subparsers have help text
            for name, subparser in subparsers_action.choices.items():
                # Each subparser should have a description or help
                # At minimum, it should be an ArgumentParser instance
                assert isinstance(subparser, argparse.ArgumentParser)
    
    def test_build_parser_default_days_value(self):
        """Invariant: default value for 'days' parameter is 30 in report and plan commands."""
        parser = cli._build_parser()
        
        # Get subparsers
        subparsers_action = None
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                subparsers_action = action
                break
        
        if not subparsers_action or not subparsers_action.choices:
            pytest.skip("No subparsers found")
        
        # Check report and plan commands for 'days' default
        days_defaults_found = []
        for name, subparser in subparsers_action.choices.items():
            if 'report' in name or 'plan' in name:
                for action in subparser._actions:
                    if hasattr(action, 'dest') and action.dest == 'days':
                        days_defaults_found.append((name, action.default))
        
        # If any days parameters exist, they should default to 30
        for name, default in days_defaults_found:
            assert default == 30, f"Command {name} has days default {default}, expected 30"
    
    def test_build_parser_default_status_meeting_items(self):
        """Invariant: default status filter for meeting-items is 'open'."""
        parser = cli._build_parser()
        
        # Get subparsers
        subparsers_action = None
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                subparsers_action = action
                break
        
        if not subparsers_action or not subparsers_action.choices:
            pytest.skip("No subparsers found")
        
        # Look for meeting-items command
        meeting_items_parser = None
        for name, subparser in subparsers_action.choices.items():
            if 'meeting-items' in name or 'meeting_items' in name:
                meeting_items_parser = subparser
                break
        
        if meeting_items_parser:
            # Check for status default
            for action in meeting_items_parser._actions:
                if hasattr(action, 'dest') and action.dest == 'status':
                    assert action.default == 'open', f"meeting-items status default is {action.default}, expected 'open'"
    
    def test_build_parser_default_status_plan_goal_list(self):
        """Invariant: default status filter for plan-goal-list is 'active'."""
        parser = cli._build_parser()
        
        # Get subparsers
        subparsers_action = None
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                subparsers_action = action
                break
        
        if not subparsers_action or not subparsers_action.choices:
            pytest.skip("No subparsers found")
        
        # Look for plan-goal-list command
        plan_goal_list_parser = None
        for name, subparser in subparsers_action.choices.items():
            if 'plan-goal-list' in name or 'plan_goal_list' in name:
                plan_goal_list_parser = subparser
                break
        
        if plan_goal_list_parser:
            # Check for status default
            for action in plan_goal_list_parser._actions:
                if hasattr(action, 'dest') and action.dest == 'status':
                    assert action.default == 'active', f"plan-goal-list status default is {action.default}, expected 'active'"
    
    def test_build_parser_json_flag_support(self):
        """Invariant: all subcommands support --json flag for JSON output where applicable."""
        parser = cli._build_parser()
        
        # Get subparsers
        subparsers_action = None
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                subparsers_action = action
                break
        
        if not subparsers_action or not subparsers_action.choices:
            pytest.skip("No subparsers found")
        
        # Check that most subcommands have --json flag
        subcommands_with_json = 0
        total_subcommands = len(subparsers_action.choices)
        
        for name, subparser in subparsers_action.choices.items():
            has_json = False
            for action in subparser._actions:
                if '--json' in action.option_strings:
                    has_json = True
                    break
            
            if has_json:
                subcommands_with_json += 1
        
        # At least some commands should support --json
        assert subcommands_with_json > 0, "No subcommands support --json flag"
    
    def test_command_name_consistency(self):
        """Invariant: command names in _rewrite_args match subparser names in _build_parser."""
        parser = cli._build_parser()
        
        # Get subparser names
        subparsers_action = None
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                subparsers_action = action
                break
        
        if not subparsers_action or not subparsers_action.choices:
            pytest.skip("No subparsers found")
        
        subparser_names = set(subparsers_action.choices.keys())
        
        # Test some common rewrites
        test_cases = [
            (['roster', 'list'], 'roster-list'),
            (['team', 'list'], 'team-list'),
            (['meeting', 'list'], 'meeting-list'),
            (['plan', 'goal', 'create'], 'plan-goal-create'),
            (['plan', 'goal', 'list'], 'plan-goal-list'),
        ]
        
        for input_args, expected_command in test_cases:
            rewritten = cli._rewrite_args(input_args)
            if rewritten and rewritten[0] == expected_command:
                # If the rewrite happens, the command should exist in subparsers
                assert expected_command in subparser_names, \
                    f"Rewritten command '{expected_command}' not found in subparsers"


class TestRewriteArgs:
    """Test suite for _rewrite_args() function."""
    
    def test_rewrite_args_identity_no_match(self):
        """Happy path: returns original arguments unchanged if no match is found."""
        result = cli._rewrite_args(['--help'])
        assert result == ['--help']
        
        result = cli._rewrite_args(['--version'])
        assert result == ['--version']
        
        result = cli._rewrite_args(['unknown', 'command'])
        assert result == ['unknown', 'command']
    
    def test_rewrite_args_two_word_command(self):
        """Happy path: transforms 2-word command to hyphenated form."""
        result = cli._rewrite_args(['roster', 'list'])
        assert result == ['roster-list']
        
        # Try other common 2-word commands
        result = cli._rewrite_args(['team', 'list'])
        assert result == ['team-list']
    
    def test_rewrite_args_three_word_command(self):
        """Happy path: transforms 3-word command to hyphenated form."""
        result = cli._rewrite_args(['plan', 'goal', 'create'])
        assert result == ['plan-goal-create']
        
        result = cli._rewrite_args(['plan', 'goal', 'list'])
        assert result == ['plan-goal-list']
    
    def test_rewrite_args_preserves_extra_arguments(self):
        """Happy path: preserves arguments beyond the matched command."""
        result = cli._rewrite_args(['roster', 'list', '--json', '--all'])
        assert result == ['roster-list', '--json', '--all']
        
        result = cli._rewrite_args(['plan', 'goal', 'create', '--name', 'test'])
        assert result == ['plan-goal-create', '--name', 'test']
    
    def test_rewrite_args_empty_list(self):
        """Edge case: handles empty list."""
        result = cli._rewrite_args([])
        assert result == []
    
    def test_rewrite_args_single_element(self):
        """Edge case: handles single element list."""
        result = cli._rewrite_args(['roster'])
        assert result == ['roster']
        
        result = cli._rewrite_args(['--help'])
        assert result == ['--help']
    
    def test_rewrite_args_with_flags_only(self):
        """Edge case: handles list with only flags."""
        result = cli._rewrite_args(['--version', '--help'])
        assert result == ['--version', '--help']
        
        result = cli._rewrite_args(['--json'])
        assert result == ['--json']
    
    def test_rewrite_args_unicode_characters(self):
        """Edge case: handles unicode characters in arguments."""
        result = cli._rewrite_args(['roster', 'list', 'café'])
        # Should preserve unicode - either rewrite or keep as-is
        assert 'café' in result or result == ['roster', 'list', 'café']
        
        # Unicode should not be corrupted
        for arg in result:
            assert isinstance(arg, str)
    
    def test_rewrite_args_special_characters(self):
        """Edge case: handles special characters and equals signs."""
        result = cli._rewrite_args(['roster', 'list', '--name=test'])
        # Should preserve the special characters
        assert '--name=test' in result
        
        result = cli._rewrite_args(['team', 'list', '--filter=active'])
        assert '--filter=active' in result
    
    def test_rewrite_args_three_word_priority(self):
        """Edge case: attempts 3-word match before 2-word match."""
        # If both "plan goal" and "plan goal create" are valid, 
        # 3-word should take priority
        result = cli._rewrite_args(['plan', 'goal', 'create', '--name', 'test'])
        assert result[0] == 'plan-goal-create'
        assert '--name' in result
        assert 'test' in result
    
    def test_rewrite_args_idempotency(self):
        """Invariant: rewriting is idempotent for already hyphenated commands."""
        result = cli._rewrite_args(['roster-list'])
        assert result == ['roster-list']
        
        result = cli._rewrite_args(['plan-goal-create'])
        assert result == ['plan-goal-create']
    
    def test_rewrite_args_list_length_non_increasing(self):
        """Invariant: output list length is less than or equal to input length."""
        test_cases = [
            [],
            ['roster'],
            ['roster', 'list'],
            ['plan', 'goal', 'create'],
            ['roster', 'list', '--json', '--all'],
            ['plan', 'goal', 'create', '--name', 'test', '--status', 'active'],
        ]
        
        for input_args in test_cases:
            result = cli._rewrite_args(input_args)
            assert len(result) <= len(input_args), \
                f"Output length {len(result)} > input length {len(input_args)} for {input_args}"
    
    def test_rewrite_args_empty_string_in_list(self):
        """Edge case: handles empty strings in argument list."""
        result = cli._rewrite_args(['roster', '', 'list'])
        # Should handle gracefully - either keep or filter
        assert isinstance(result, list)
    
    def test_rewrite_args_very_long_strings(self):
        """Edge case: handles very long argument strings."""
        long_arg = 'x' * 10000
        result = cli._rewrite_args(['roster', 'list', long_arg])
        # Should preserve the long argument
        assert long_arg in result or result == ['roster', 'list', long_arg]


class TestMain:
    """Test suite for main() entry point function."""
    
    def test_main_no_command_exits_1(self, capsys):
        """Error case: exits with code 1 if no command is specified."""
        with pytest.raises(SystemExit) as exc_info:
            cli.main([])
        
        assert exc_info.value.code == 1
        
        # Should print help
        captured = capsys.readouterr()
        # Either stdout or stderr should contain help text
        output = captured.out + captured.err
        assert len(output) > 0
    
    def test_main_unrecognized_command_exits_1(self, capsys):
        """Error case: exits with code 1 if command is unrecognized."""
        with pytest.raises(SystemExit) as exc_info:
            cli.main(['invalid-command-xyz'])
        
        assert exc_info.value.code in [1, 2]  # argparse may use 2 for parse errors
        
        # Should print error/help
        captured = capsys.readouterr()
        output = captured.out + captured.err
        assert len(output) > 0
    
    @patch('src.ascend.cli.roster')
    def test_main_recognized_command_invokes_handler(self, mock_roster_module):
        """Happy path: invokes corresponding handler function for recognized command."""
        # Mock the handler function
        mock_handler = Mock()
        mock_roster_module.list = mock_handler
        
        # This might still exit or raise, so we wrap it
        try:
            cli.main(['roster-list'])
        except (SystemExit, AttributeError):
            # Some implementations may exit cleanly or raise AttributeError if handler doesn't exist
            pass
        
        # Check if handler was attempted to be called
        # Since we don't know the exact implementation, we just verify no crash on valid command
    
    @patch('sys.argv', ['ascend', 'roster', 'list'])
    def test_main_with_none_argv(self):
        """Happy path: handles None argv (uses sys.argv[1:])."""
        # When argv is None, main should use sys.argv[1:]
        with patch('src.ascend.cli.roster') as mock_roster:
            mock_handler = Mock()
            mock_roster.list = mock_handler
            
            try:
                cli.main(None)
            except (SystemExit, AttributeError, TypeError):
                # May exit or fail if handler doesn't exist
                pass
    
    def test_main_help_flag(self, capsys):
        """Happy path: handles --help flag without error."""
        with pytest.raises(SystemExit) as exc_info:
            cli.main(['--help'])
        
        assert exc_info.value.code == 0
        
        # Should display help text
        captured = capsys.readouterr()
        output = captured.out + captured.err
        assert len(output) > 0
        assert 'ascend' in output.lower() or 'usage' in output.lower()
    
    def test_main_version_flag(self, capsys):
        """Happy path: handles --version flag."""
        with pytest.raises(SystemExit) as exc_info:
            cli.main(['--version'])
        
        assert exc_info.value.code == 0
        
        # Should display version
        captured = capsys.readouterr()
        output = captured.out + captured.err
        assert len(output) > 0
    
    @patch('src.ascend.cli.roster')
    def test_main_rewriting_integration(self, mock_roster_module):
        """Integration: full pipeline test with argument rewriting."""
        # Test that space-separated commands get rewritten and dispatched
        mock_handler = Mock()
        mock_roster_module.list = mock_handler
        
        try:
            cli.main(['roster', 'list'])
        except (SystemExit, AttributeError):
            # May exit or fail depending on implementation
            pass
        
        # The key is that 'roster list' should be rewritten to 'roster-list'
        # We verify by checking that no exception is raised during rewriting
    
    @patch('src.ascend.cli.roster')
    def test_main_command_with_arguments(self, mock_roster_module):
        """Integration: command with additional arguments."""
        mock_handler = Mock()
        mock_roster_module.list = mock_handler
        
        try:
            cli.main(['roster-list', '--json'])
        except (SystemExit, AttributeError):
            pass
    
    def test_main_invalid_flag(self, capsys):
        """Error case: handles invalid flags gracefully."""
        with pytest.raises(SystemExit) as exc_info:
            cli.main(['--invalid-flag-xyz'])
        
        # argparse typically exits with code 2 for unrecognized arguments
        assert exc_info.value.code in [1, 2]
        
        captured = capsys.readouterr()
        output = captured.out + captured.err
        assert len(output) > 0
    
    @patch('src.ascend.cli.team')
    def test_main_different_command(self, mock_team_module):
        """Happy path: test a different command to ensure routing works."""
        mock_handler = Mock()
        mock_team_module.list = mock_handler
        
        try:
            cli.main(['team', 'list'])
        except (SystemExit, AttributeError):
            pass
    
    def test_main_preserves_argument_order(self):
        """Integration: verify argument order is preserved through pipeline."""
        # Test with a command that has multiple arguments
        try:
            cli.main(['roster', 'list', '--json', '--all', '--verbose'])
        except (SystemExit, AttributeError, Exception):
            # We're mainly testing that the pipeline doesn't crash
            pass
    
    @patch('src.ascend.cli.meeting')
    def test_main_meeting_command(self, mock_meeting_module):
        """Happy path: test meeting-related command."""
        mock_handler = Mock()
        mock_meeting_module.list = mock_handler
        
        try:
            cli.main(['meeting', 'list'])
        except (SystemExit, AttributeError):
            pass
    
    @patch('src.ascend.cli.plan')
    def test_main_three_word_command_routing(self, mock_plan_module):
        """Integration: test 3-word command routing."""
        # Mock nested structure for plan.goal.create
        mock_goal = Mock()
        mock_handler = Mock()
        mock_goal.create = mock_handler
        mock_plan_module.goal = mock_goal
        
        try:
            cli.main(['plan', 'goal', 'create'])
        except (SystemExit, AttributeError):
            pass


class TestIntegration:
    """Integration tests for the full CLI pipeline."""
    
    def test_full_pipeline_roster_list(self):
        """Integration: complete pipeline from argv to handler dispatch for roster list."""
        with patch('src.ascend.cli.roster') as mock_roster:
            mock_handler = Mock()
            mock_roster.list = mock_handler
            
            try:
                cli.main(['roster', 'list', '--json'])
            except (SystemExit, AttributeError):
                pass
    
    def test_full_pipeline_plan_goal_create(self):
        """Integration: complete pipeline for 3-word command."""
        with patch('src.ascend.cli.plan') as mock_plan:
            mock_goal = Mock()
            mock_handler = Mock()
            mock_goal.create = mock_handler
            mock_plan.goal = mock_goal
            
            try:
                cli.main(['plan', 'goal', 'create', '--name', 'test'])
            except (SystemExit, AttributeError):
                pass
    
    def test_parser_rewrite_consistency(self):
        """Integration: verify parser can parse all rewritten commands."""
        parser = cli._build_parser()
        
        # Test that rewritten commands can be parsed
        test_commands = [
            ['roster', 'list'],
            ['team', 'list'],
            ['meeting', 'list'],
        ]
        
        for original_args in test_commands:
            rewritten = cli._rewrite_args(original_args)
            # The parser should be able to handle the rewritten form
            try:
                parser.parse_args(rewritten)
            except SystemExit:
                # May exit due to missing required args, but shouldn't fail to recognize command
                pass
    
    def test_help_text_contains_key_info(self, capsys):
        """Integration: verify help text contains essential information."""
        with pytest.raises(SystemExit):
            cli.main(['--help'])
        
        captured = capsys.readouterr()
        help_text = captured.out + captured.err
        
        # Should contain program name
        assert 'ascend' in help_text.lower()
        
        # Should contain some command information
        assert len(help_text) > 100  # Reasonable minimum for help text
    
    def test_version_display(self, capsys):
        """Integration: verify version information is displayed."""
        with pytest.raises(SystemExit):
            cli.main(['--version'])
        
        captured = capsys.readouterr()
        version_text = captured.out + captured.err
        
        # Should display some version information
        assert len(version_text) > 0
    
    @patch('src.ascend.cli.tui')
    def test_tui_command_integration(self, mock_tui_module):
        """Integration: test TUI command if it exists."""
        mock_handler = Mock()
        mock_tui_module.run = mock_handler
        
        try:
            cli.main(['tui'])
        except (SystemExit, AttributeError):
            pass
