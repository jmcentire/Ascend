"""
Contract tests for src_ascend_config module.

Tests verify behavior at boundaries including happy paths, edge cases,
error cases, and invariants as defined in the contract.
"""

import pytest
import yaml
import tempfile
import shutil
from pathlib import Path
from typing import Optional
from unittest.mock import Mock, patch, mock_open, MagicMock
from pydantic import ValidationError

# Import the component under test
from src.ascend.config import (
    AscendConfig,
    load_config,
    save_config,
    get_config_value,
    set_config_value,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary directory for config files."""
    config_dir = tmp_path / "test_ascend"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


@pytest.fixture
def valid_config():
    """Create a valid AscendConfig instance for testing."""
    return AscendConfig(
        repos_dir="/tmp/repos",
        reports_dir="/tmp/reports",
        config_dir="/tmp/config",
        anthropic_api_key_env="ANTHROPIC_API_KEY",
        model="claude-3-sonnet-20240229",
        default_lookback_hours=24,
        linear_team_id="TEAM123",
        linear_api_key_env="LINEAR_API_KEY",
        linear_team_ids=["TEAM1", "TEAM2"],
        slack_channels=["#general", "#dev"],
        slack_bot_token_env="SLACK_BOT_TOKEN",
        github_org="test-org",
        manager_name="Test Manager"
    )


@pytest.fixture
def valid_yaml_content():
    """Valid YAML config content."""
    return """
repos_dir: /custom/repos
model: claude-3-opus-20240229
default_lookback_hours: 48
slack_channels:
  - "#alerts"
  - "#monitoring"
"""


@pytest.fixture
def malformed_yaml_content():
    """Malformed YAML content for error testing."""
    return """
repos_dir: /test
  bad_indent: value
model: [unclosed bracket
"""


@pytest.fixture
def yaml_with_nones():
    """YAML content with None values."""
    return """
repos_dir: /test/repos
model: null
slack_channels: null
linear_team_ids:
  - "TEAM1"
"""


@pytest.fixture
def invalid_values_yaml():
    """YAML with invalid field values for Pydantic validation."""
    return """
default_lookback_hours: "not_an_integer"
"""


@pytest.fixture
def empty_yaml_content():
    """Empty YAML file content."""
    return ""


# ============================================================================
# Happy Path Tests - load_config
# ============================================================================

def test_load_config_default_path_no_file(temp_config_dir):
    """Load config when no file exists at default path, should return AscendConfig with defaults."""
    with patch('src_ascend_config.CONFIG_PATH', temp_config_dir / "config.yaml"):
        config = load_config(None)
        
        # Should return a valid AscendConfig instance
        assert isinstance(config, AscendConfig)
        
        # Should have default values for required fields
        assert config.repos_dir is not None
        assert config.reports_dir is not None
        assert config.config_dir is not None
        assert config.anthropic_api_key_env is not None
        assert config.model is not None
        assert isinstance(config.default_lookback_hours, int)


def test_load_config_valid_yaml(temp_config_dir, valid_yaml_content):
    """Load config from valid YAML file with partial config."""
    config_file = temp_config_dir / "config.yaml"
    config_file.write_text(valid_yaml_content)
    
    config = load_config(config_file)
    
    # Should merge values from file with defaults
    assert isinstance(config, AscendConfig)
    assert config.repos_dir == "/custom/repos"
    assert config.model == "claude-3-opus-20240229"
    assert config.default_lookback_hours == 48
    assert "#alerts" in config.slack_channels
    
    # Default values should still be present for unspecified fields
    assert config.anthropic_api_key_env is not None
    assert config.github_org is not None


def test_load_config_filters_none_values(temp_config_dir, yaml_with_nones):
    """Load config with None values in YAML, should filter them out."""
    config_file = temp_config_dir / "config.yaml"
    config_file.write_text(yaml_with_nones)
    
    config = load_config(config_file)
    
    # None values should be filtered and defaults used
    assert isinstance(config, AscendConfig)
    assert config.repos_dir == "/test/repos"  # From file
    assert config.model is not None  # Default, not None
    assert config.slack_channels is not None  # Default, not None
    assert "TEAM1" in config.linear_team_ids


def test_load_config_empty_yaml(temp_config_dir, empty_yaml_content):
    """Load config from empty YAML file."""
    config_file = temp_config_dir / "config.yaml"
    config_file.write_text(empty_yaml_content)
    
    config = load_config(config_file)
    
    # Should return config with all defaults
    assert isinstance(config, AscendConfig)
    assert config.model is not None
    assert config.repos_dir is not None


# ============================================================================
# Error Tests - load_config
# ============================================================================

def test_load_config_malformed_yaml(temp_config_dir, malformed_yaml_content):
    """Load config from malformed YAML file."""
    config_file = temp_config_dir / "malformed.yaml"
    config_file.write_text(malformed_yaml_content)
    
    with pytest.raises(Exception) as exc_info:
        load_config(config_file)
    
    # Should raise yaml_parse_error
    assert "yaml" in str(exc_info.typename).lower() or "parse" in str(exc_info.value).lower()


def test_load_config_invalid_values(temp_config_dir, invalid_values_yaml):
    """Load config with invalid field values for Pydantic validation."""
    config_file = temp_config_dir / "invalid.yaml"
    config_file.write_text(invalid_values_yaml)
    
    with pytest.raises((ValidationError, ValueError)) as exc_info:
        load_config(config_file)
    
    # Should raise pydantic_validation_error
    assert exc_info.type in (ValidationError, ValueError)


def test_load_config_permission_denied(temp_config_dir):
    """Load config when file exists but cannot be read."""
    config_file = temp_config_dir / "unreadable.yaml"
    config_file.write_text("model: test")
    config_file.chmod(0o000)
    
    try:
        with pytest.raises((PermissionError, OSError, IOError)) as exc_info:
            load_config(config_file)
        
        # Should raise io_error
        assert exc_info.type in (PermissionError, OSError, IOError)
    finally:
        config_file.chmod(0o644)


# ============================================================================
# Happy Path Tests - save_config
# ============================================================================

def test_save_config_default_path(temp_config_dir, valid_config):
    """Save config to default path, creating parent directories."""
    config_path = temp_config_dir / "config.yaml"
    
    with patch('src_ascend_config.CONFIG_PATH', config_path):
        save_config(valid_config, None)
        
        # Config file should exist
        assert config_path.exists()
        
        # Should contain YAML content
        content = config_path.read_text()
        assert "repos_dir" in content
        assert "model" in content
        
        # Verify it's valid YAML
        data = yaml.safe_load(content)
        assert data is not None
        assert data.get("model") == valid_config.model


def test_save_config_custom_path(temp_config_dir, valid_config):
    """Save config to custom path with parent directory creation."""
    custom_path = temp_config_dir / "custom" / "path" / "config.yaml"
    
    save_config(valid_config, custom_path)
    
    # Parent directories should be created
    assert custom_path.parent.exists()
    
    # Config file should exist
    assert custom_path.exists()
    
    # Verify content
    content = custom_path.read_text()
    data = yaml.safe_load(content)
    assert data.get("repos_dir") == valid_config.repos_dir


def test_save_config_yaml_format(temp_config_dir, valid_config):
    """Verify saved YAML uses non-flow style."""
    config_path = temp_config_dir / "test.yaml"
    
    save_config(valid_config, config_path)
    
    content = config_path.read_text()
    
    # Should use block style for lists, not flow style
    # Block style: "- item" not "[item1, item2]"
    if valid_config.slack_channels:
        assert "- " in content or not any("[" in line and "]" in line for line in content.split("\n"))


def test_round_trip_save_load(temp_config_dir, valid_config):
    """Save and load config preserves all values."""
    config_path = temp_config_dir / "roundtrip.yaml"
    
    # Save config
    save_config(valid_config, config_path)
    
    # Load it back
    loaded_config = load_config(config_path)
    
    # All values should be preserved
    assert loaded_config.repos_dir == valid_config.repos_dir
    assert loaded_config.model == valid_config.model
    assert loaded_config.default_lookback_hours == valid_config.default_lookback_hours
    assert loaded_config.slack_channels == valid_config.slack_channels
    assert loaded_config.linear_team_ids == valid_config.linear_team_ids
    assert loaded_config.manager_name == valid_config.manager_name


# ============================================================================
# Error Tests - save_config
# ============================================================================

def test_save_config_io_error(temp_config_dir, valid_config):
    """Save config when file cannot be written due to permissions."""
    # Create a read-only file
    config_path = temp_config_dir / "readonly.yaml"
    config_path.write_text("test")
    config_path.chmod(0o444)
    
    # Make parent directory read-only too
    temp_config_dir.chmod(0o555)
    
    try:
        with pytest.raises((PermissionError, OSError, IOError)):
            save_config(valid_config, config_path)
    finally:
        temp_config_dir.chmod(0o755)
        config_path.chmod(0o644)


def test_save_config_cannot_create_dirs(temp_config_dir, valid_config):
    """Save config when parent directories cannot be created."""
    # Create a file where we need a directory
    blocking_file = temp_config_dir / "blocking"
    blocking_file.write_text("block")
    
    config_path = temp_config_dir / "blocking" / "config.yaml"
    
    with pytest.raises((NotADirectoryError, OSError, FileExistsError)):
        save_config(valid_config, config_path)


# ============================================================================
# Happy Path Tests - get_config_value
# ============================================================================

def test_get_config_value_valid_key(valid_config):
    """Get config value for valid key with provided config."""
    value = get_config_value("model", valid_config)
    
    # Should return string representation
    assert isinstance(value, str)
    assert value == valid_config.model


def test_get_config_value_load_from_disk(temp_config_dir, valid_yaml_content):
    """Get config value when cfg is None, loads from disk."""
    config_path = temp_config_dir / "config.yaml"
    config_path.write_text(valid_yaml_content)
    
    with patch('src_ascend_config.CONFIG_PATH', config_path):
        value = get_config_value("repos_dir", None)
        
        # Should load from disk and return value
        assert isinstance(value, str)
        assert value == "/custom/repos"


def test_get_config_value_list_field(valid_config):
    """Get config value for list field returns string representation."""
    value = get_config_value("slack_channels", valid_config)
    
    # Should return string representation of list
    assert isinstance(value, str)
    assert "#general" in value or "general" in value


def test_get_config_value_optional_field(valid_config):
    """Get config value for optional field (manager_name)."""
    value = get_config_value("manager_name", valid_config)
    
    # Should return string representation
    assert isinstance(value, str)
    assert value == "Test Manager"


# ============================================================================
# Error Tests - get_config_value
# ============================================================================

def test_get_config_value_invalid_key(valid_config):
    """Get config value with invalid field name."""
    with pytest.raises((KeyError, AttributeError)) as exc_info:
        get_config_value("nonexistent_field", valid_config)
    
    # Should raise key_error
    assert exc_info.type in (KeyError, AttributeError)


def test_get_config_value_malformed_yaml(temp_config_dir, malformed_yaml_content):
    """Get config value when cfg is None and config file is malformed."""
    config_path = temp_config_dir / "malformed.yaml"
    config_path.write_text(malformed_yaml_content)
    
    with patch('src_ascend_config.CONFIG_PATH', config_path):
        with pytest.raises(Exception) as exc_info:
            get_config_value("model", None)
        
        # Should raise yaml_parse_error
        assert "yaml" in str(exc_info.typename).lower() or "parse" in str(exc_info.value).lower()


def test_get_config_value_io_error(temp_config_dir):
    """Get config value when cfg is None and cannot read config file."""
    config_path = temp_config_dir / "unreadable.yaml"
    config_path.write_text("model: test")
    config_path.chmod(0o000)
    
    with patch('src_ascend_config.CONFIG_PATH', config_path):
        try:
            with pytest.raises((PermissionError, OSError, IOError)):
                get_config_value("model", None)
        finally:
            config_path.chmod(0o644)


# ============================================================================
# Happy Path Tests - set_config_value
# ============================================================================

def test_set_config_value_string_field(temp_config_dir):
    """Set config value for string field."""
    config_path = temp_config_dir / "config.yaml"
    
    updated_config = set_config_value("model", "claude-3-opus-20240229", config_path)
    
    # Should return updated AscendConfig
    assert isinstance(updated_config, AscendConfig)
    assert updated_config.model == "claude-3-opus-20240229"
    
    # Config should be saved
    assert config_path.exists()


def test_set_config_value_int_field(temp_config_dir):
    """Set config value for int field with type coercion."""
    config_path = temp_config_dir / "config.yaml"
    
    updated_config = set_config_value("default_lookback_hours", "48", config_path)
    
    # Should coerce to int
    assert isinstance(updated_config, AscendConfig)
    assert updated_config.default_lookback_hours == 48
    assert isinstance(updated_config.default_lookback_hours, int)


def test_set_config_value_list_field(temp_config_dir):
    """Set config value for list field with comma-separated values."""
    config_path = temp_config_dir / "config.yaml"
    
    updated_config = set_config_value("slack_channels", "#general,#dev,#alerts", config_path)
    
    # Should split by comma and create list
    assert isinstance(updated_config, AscendConfig)
    assert isinstance(updated_config.slack_channels, list)
    assert "#general" in updated_config.slack_channels
    assert "#dev" in updated_config.slack_channels
    assert "#alerts" in updated_config.slack_channels


def test_set_config_value_empty_list(temp_config_dir):
    """Set list field with empty string."""
    config_path = temp_config_dir / "config.yaml"
    
    updated_config = set_config_value("slack_channels", "", config_path)
    
    # Should handle empty string
    assert isinstance(updated_config, AscendConfig)
    assert isinstance(updated_config.slack_channels, list)


# ============================================================================
# Error Tests - set_config_value
# ============================================================================

def test_set_config_value_invalid_key(temp_config_dir):
    """Set config value with invalid field name."""
    config_path = temp_config_dir / "config.yaml"
    
    with pytest.raises((KeyError, AttributeError)) as exc_info:
        set_config_value("invalid_field", "test", config_path)
    
    assert exc_info.type in (KeyError, AttributeError)


def test_set_config_value_invalid_int(temp_config_dir):
    """Set int field with non-numeric value."""
    config_path = temp_config_dir / "config.yaml"
    
    with pytest.raises((ValueError, ValidationError)) as exc_info:
        set_config_value("default_lookback_hours", "not_a_number", config_path)
    
    assert exc_info.type in (ValueError, ValidationError)


def test_set_config_value_pydantic_validation_fails(temp_config_dir):
    """Set value that fails Pydantic validation."""
    config_path = temp_config_dir / "config.yaml"
    
    with pytest.raises((ValidationError, ValueError)):
        # Negative hours might fail validation
        set_config_value("default_lookback_hours", "-100", config_path)


def test_set_config_value_malformed_existing_yaml(temp_config_dir, malformed_yaml_content):
    """Set value when existing config file has malformed YAML."""
    config_path = temp_config_dir / "config.yaml"
    config_path.write_text(malformed_yaml_content)
    
    with pytest.raises(Exception) as exc_info:
        set_config_value("model", "new-model", config_path)
    
    # Should raise yaml_parse_error
    assert "yaml" in str(exc_info.typename).lower() or "parse" in str(exc_info.value).lower()


def test_set_config_value_io_error(temp_config_dir):
    """Set value when cannot read or write config file."""
    config_path = temp_config_dir / "unwritable.yaml"
    config_path.write_text("model: test")
    config_path.chmod(0o444)
    
    temp_config_dir.chmod(0o555)
    
    try:
        with pytest.raises((PermissionError, OSError, IOError)):
            set_config_value("model", "new-model", config_path)
    finally:
        temp_config_dir.chmod(0o755)
        config_path.chmod(0o644)


# ============================================================================
# Invariant Tests
# ============================================================================

def test_invariant_ascend_home():
    """Verify ASCEND_HOME is always ~/.ascend."""
    from src.ascend.config import ASCEND_HOME
    
    expected_home = Path.home() / ".ascend"
    assert ASCEND_HOME == expected_home


def test_invariant_config_path():
    """Verify CONFIG_PATH is always ~/.ascend/config.yaml."""
    from src.ascend.config import CONFIG_PATH
    
    expected_path = Path.home() / ".ascend" / "config.yaml"
    assert CONFIG_PATH == expected_path


def test_invariant_db_path():
    """Verify DB_PATH is always ~/.ascend/ascend.db."""
    from src.ascend.config import DB_PATH
    
    expected_path = Path.home() / ".ascend" / "ascend.db"
    assert DB_PATH == expected_path


def test_invariant_history_dir():
    """Verify HISTORY_DIR is always ~/.ascend/history."""
    from src.ascend.config import HISTORY_DIR
    
    expected_path = Path.home() / ".ascend" / "history"
    assert HISTORY_DIR == expected_path


def test_invariant_transcripts_dir():
    """Verify TRANSCRIPTS_DIR is always ~/.ascend/transcripts."""
    from src.ascend.config import TRANSCRIPTS_DIR
    
    expected_path = Path.home() / ".ascend" / "transcripts"
    assert TRANSCRIPTS_DIR == expected_path


def test_invariant_schedules_dir():
    """Verify SCHEDULES_DIR is always ~/.ascend/schedules."""
    from src.ascend.config import SCHEDULES_DIR
    
    expected_path = Path.home() / ".ascend" / "schedules"
    assert SCHEDULES_DIR == expected_path


def test_invariant_no_none_values(temp_config_dir):
    """Verify config values are never None after load_config."""
    config_path = temp_config_dir / "config.yaml"
    config_path.write_text("repos_dir: /test")
    
    config = load_config(config_path)
    
    # Required fields should never be None
    assert config.repos_dir is not None
    assert config.reports_dir is not None
    assert config.config_dir is not None
    assert config.anthropic_api_key_env is not None
    assert config.model is not None
    assert config.default_lookback_hours is not None
    assert config.linear_team_id is not None
    assert config.linear_api_key_env is not None
    assert config.linear_team_ids is not None
    assert config.slack_channels is not None
    assert config.slack_bot_token_env is not None
    assert config.github_org is not None
    # manager_name is Optional, so it can be None


def test_invariant_defaults_exist():
    """Verify _DEFAULTS dict provides fallback values."""
    from src.ascend.config import _DEFAULTS
    
    # _DEFAULTS should exist and contain values
    assert isinstance(_DEFAULTS, dict)
    assert len(_DEFAULTS) > 0
    
    # Should have defaults for key fields
    assert "repos_dir" in _DEFAULTS
    assert "model" in _DEFAULTS
    assert "default_lookback_hours" in _DEFAULTS


def test_invariant_type_coercion_rules(temp_config_dir):
    """Verify type coercion in set_config_value works correctly."""
    config_path = temp_config_dir / "config.yaml"
    
    # Test int field coercion
    config_int = set_config_value("default_lookback_hours", "72", config_path)
    assert isinstance(config_int.default_lookback_hours, int)
    assert config_int.default_lookback_hours == 72
    
    # Test list field coercion
    config_list = set_config_value("linear_team_ids", "TEAM1,TEAM2,TEAM3", config_path)
    assert isinstance(config_list.linear_team_ids, list)
    assert len(config_list.linear_team_ids) == 3
    
    # Test string field remains string
    config_str = set_config_value("model", "test-model", config_path)
    assert isinstance(config_str.model, str)
    assert config_str.model == "test-model"


# ============================================================================
# Additional Edge Cases
# ============================================================================

def test_load_config_with_custom_path(temp_config_dir, valid_yaml_content):
    """Load config from custom path."""
    custom_path = temp_config_dir / "custom.yaml"
    custom_path.write_text(valid_yaml_content)
    
    config = load_config(custom_path)
    
    assert isinstance(config, AscendConfig)
    assert config.repos_dir == "/custom/repos"


def test_save_config_overwrites_existing(temp_config_dir, valid_config):
    """Save config overwrites existing file."""
    config_path = temp_config_dir / "config.yaml"
    config_path.write_text("old: data")
    
    save_config(valid_config, config_path)
    
    # Old content should be overwritten
    content = config_path.read_text()
    assert "old: data" not in content
    assert "model:" in content


def test_config_preserves_all_fields(valid_config):
    """Verify AscendConfig has all expected fields."""
    assert hasattr(valid_config, "repos_dir")
    assert hasattr(valid_config, "reports_dir")
    assert hasattr(valid_config, "config_dir")
    assert hasattr(valid_config, "anthropic_api_key_env")
    assert hasattr(valid_config, "model")
    assert hasattr(valid_config, "default_lookback_hours")
    assert hasattr(valid_config, "linear_team_id")
    assert hasattr(valid_config, "linear_api_key_env")
    assert hasattr(valid_config, "linear_team_ids")
    assert hasattr(valid_config, "slack_channels")
    assert hasattr(valid_config, "slack_bot_token_env")
    assert hasattr(valid_config, "github_org")
    assert hasattr(valid_config, "manager_name")


def test_set_config_value_whitespace_handling(temp_config_dir):
    """Test that set_config_value handles whitespace in comma-separated lists."""
    config_path = temp_config_dir / "config.yaml"
    
    # Test with spaces around commas
    config = set_config_value("slack_channels", "#general , #dev , #alerts", config_path)
    
    # Should handle whitespace properly
    assert isinstance(config.slack_channels, list)
    # Values might be trimmed or preserved depending on implementation
    assert len(config.slack_channels) >= 3
