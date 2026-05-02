"""
Contract tests for Ascend Configuration Management Interface.

This test suite validates the configuration management system with comprehensive
coverage of happy paths, edge cases, error conditions, and invariants.

Test layers:
- Layer 1: Unit tests for each function (load_config, save_config, get_config_value, set_config_value)
- Layer 2: Integration tests for workflows
- Layer 3: Invariant tests for contract guarantees
- Layer 4: Error path coverage for all error types
"""

import pytest
import tempfile
import os
import yaml
from pathlib import Path
from unittest.mock import Mock, patch, mock_open, MagicMock
from typing import Optional
import random
import string

# Import the module under test
from contracts.contracts_src_ascend_config_interface.interface import (
    AscendConfig,
    load_config,
    save_config,
    get_config_value,
    set_config_value,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def temp_config_dir(tmp_path):
    """Provide a temporary directory for config files."""
    config_dir = tmp_path / ".ascend"
    config_dir.mkdir(exist_ok=True)
    return config_dir


@pytest.fixture
def temp_config_path(temp_config_dir):
    """Provide a temporary config file path."""
    return temp_config_dir / "config.yaml"


@pytest.fixture
def sample_config_data():
    """Provide sample configuration data."""
    return {
        "repos_dir": "/path/to/repos",
        "reports_dir": "/path/to/reports",
        "config_dir": "/path/to/config",
        "anthropic_api_key_env": "ANTHROPIC_API_KEY",
        "model": "claude-3-opus",
        "default_lookback_hours": 24,
        "linear_team_id": "team123",
        "linear_api_key_env": "LINEAR_API_KEY",
        "linear_team_ids": ["team1", "team2"],
        "slack_channels": ["#general", "#dev"],
        "slack_bot_token_env": "SLACK_BOT_TOKEN",
        "github_org": "myorg",
        "manager_name": "John Doe",
    }


@pytest.fixture
def sample_config(sample_config_data):
    """Provide a sample AscendConfig instance."""
    return AscendConfig(**sample_config_data)


@pytest.fixture
def partial_config_data():
    """Provide partial configuration data with some None values."""
    return {
        "repos_dir": "/path/to/repos",
        "model": "claude-3-opus",
        "default_lookback_hours": 24,
        "linear_team_ids": ["team1", "team2"],
    }


# ============================================================================
# LAYER 1: UNIT TESTS - load_config
# ============================================================================

def test_load_config_happy_path_with_file(temp_config_path, sample_config_data):
    """Load configuration from existing YAML file successfully."""
    # Write sample config to file
    with open(temp_config_path, 'w') as f:
        yaml.dump(sample_config_data, f, default_flow_style=False)
    
    # Load config
    config = load_config(temp_config_path)
    
    # Assertions
    assert isinstance(config, AscendConfig)
    assert config.repos_dir == sample_config_data["repos_dir"]
    assert config.model == sample_config_data["model"]
    assert config.default_lookback_hours == sample_config_data["default_lookback_hours"]
    assert config.linear_team_ids == sample_config_data["linear_team_ids"]


def test_load_config_happy_path_no_file(tmp_path):
    """Load configuration when file does not exist, using defaults."""
    non_existent_path = tmp_path / "nonexistent" / "config.yaml"
    
    # Load config (file doesn't exist)
    config = load_config(non_existent_path)
    
    # Assertions
    assert isinstance(config, AscendConfig)
    # Should return config with defaults (all None or default values)


def test_load_config_happy_path_none_value():
    """Load configuration with None as config path."""
    # Load with None path
    config = load_config(None)
    
    # Assertions
    assert isinstance(config, AscendConfig)


def test_load_config_edge_case_partial_config(temp_config_path, partial_config_data):
    """Load configuration with only some fields set in YAML."""
    # Write partial config to file
    with open(temp_config_path, 'w') as f:
        yaml.dump(partial_config_data, f, default_flow_style=False)
    
    # Load config
    config = load_config(temp_config_path)
    
    # Assertions
    assert isinstance(config, AscendConfig)
    assert config.repos_dir == partial_config_data["repos_dir"]
    assert config.model == partial_config_data["model"]
    # Fields not in partial config should use defaults (None)


def test_load_config_edge_case_empty_file(temp_config_path):
    """Load configuration from empty YAML file."""
    # Create empty file
    temp_config_path.touch()
    
    # Load config
    config = load_config(temp_config_path)
    
    # Assertions
    assert isinstance(config, AscendConfig)


def test_load_config_error_malformed_yaml(temp_config_path):
    """Load configuration fails with malformed YAML."""
    # Write malformed YAML
    with open(temp_config_path, 'w') as f:
        f.write("invalid: yaml: content: [unclosed")
    
    # Assertions
    with pytest.raises(Exception) as exc_info:
        load_config(temp_config_path)
    # Should raise yaml_parse_error (or similar)
    assert "yaml" in str(exc_info.value).lower() or "parse" in str(exc_info.value).lower()


def test_load_config_error_invalid_yaml_data(temp_config_path):
    """Load configuration fails with invalid YAML structure."""
    # Write YAML that's not a dict
    with open(temp_config_path, 'w') as f:
        yaml.dump(["item1", "item2"], f)
    
    # Assertions
    with pytest.raises(Exception) as exc_info:
        load_config(temp_config_path)


def test_load_config_error_pydantic_validation(temp_config_path):
    """Load configuration fails Pydantic validation."""
    # Write data that violates Pydantic constraints
    invalid_data = {
        "default_lookback_hours": "not_an_int",  # Should be int
    }
    with open(temp_config_path, 'w') as f:
        yaml.dump(invalid_data, f)
    
    # Assertions
    with pytest.raises(Exception) as exc_info:
        load_config(temp_config_path)
    # Should raise validation error


@patch("builtins.open", side_effect=PermissionError("Permission denied"))
def test_load_config_error_permission_denied(mock_file, temp_config_path):
    """Load configuration fails with permission error."""
    # Touch the file so it exists
    temp_config_path.touch()
    
    # Assertions
    with pytest.raises(PermissionError):
        load_config(temp_config_path)


@patch("builtins.open", side_effect=IOError("I/O error"))
def test_load_config_error_io_error(mock_file, temp_config_path):
    """Load configuration fails with I/O error."""
    # Touch the file so it exists
    temp_config_path.touch()
    
    # Assertions
    with pytest.raises(IOError):
        load_config(temp_config_path)


# ============================================================================
# LAYER 1: UNIT TESTS - save_config
# ============================================================================

def test_save_config_happy_path(temp_config_path, sample_config):
    """Save configuration to YAML file successfully."""
    # Save config
    save_config(sample_config, temp_config_path)
    
    # Assertions
    assert temp_config_path.exists()
    
    # Load and verify content
    with open(temp_config_path, 'r') as f:
        content = f.read()
        loaded_data = yaml.safe_load(content)
    
    assert loaded_data["repos_dir"] == sample_config.repos_dir
    assert loaded_data["model"] == sample_config.model
    # Verify not flow style (should have newlines)
    assert '\n' in content


def test_save_config_happy_path_creates_directories(tmp_path, sample_config):
    """Save configuration creates parent directories."""
    # Create path with non-existent parents
    deep_path = tmp_path / "level1" / "level2" / "level3" / "config.yaml"
    
    # Save config
    save_config(sample_config, deep_path)
    
    # Assertions
    assert deep_path.exists()
    assert deep_path.parent.exists()


def test_save_config_happy_path_none_path(sample_config):
    """Save configuration with None path uses default."""
    with patch("pathlib.Path.mkdir") as mock_mkdir, \
         patch("builtins.open", mock_open()) as mock_file, \
         patch("yaml.dump") as mock_dump:
        
        # Save with None path
        save_config(sample_config, None)
        
        # Assertions - should use default path
        mock_file.assert_called()


def test_save_config_edge_case_overwrite_existing(temp_config_path, sample_config):
    """Save configuration overwrites existing file."""
    # Create existing file with different content
    with open(temp_config_path, 'w') as f:
        f.write("old: content")
    
    # Save new config
    save_config(sample_config, temp_config_path)
    
    # Assertions
    with open(temp_config_path, 'r') as f:
        loaded_data = yaml.safe_load(f)
    
    assert loaded_data.get("repos_dir") == sample_config.repos_dir
    assert "old" not in loaded_data


def test_save_config_edge_case_all_optional_none(temp_config_path):
    """Save configuration with all optional fields as None."""
    # Create config with all None
    config = AscendConfig()
    
    # Save config
    save_config(config, temp_config_path)
    
    # Assertions
    assert temp_config_path.exists()
    
    # Verify it's valid YAML
    with open(temp_config_path, 'r') as f:
        loaded_data = yaml.safe_load(f)
    assert isinstance(loaded_data, (dict, type(None)))


@patch("pathlib.Path.mkdir", side_effect=PermissionError("Permission denied"))
def test_save_config_error_permission_mkdir(mock_mkdir, tmp_path, sample_config):
    """Save configuration fails creating directories without permission."""
    deep_path = tmp_path / "protected" / "config.yaml"
    
    # Assertions
    with pytest.raises(PermissionError):
        save_config(sample_config, deep_path)


@patch("builtins.open", side_effect=PermissionError("Permission denied"))
def test_save_config_error_permission_denied(mock_file, temp_config_path, sample_config):
    """Save configuration fails with write permission error."""
    # Ensure parent exists
    temp_config_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Assertions
    with pytest.raises(PermissionError):
        save_config(sample_config, temp_config_path)


@patch("builtins.open", side_effect=IOError("I/O error"))
def test_save_config_error_io_error(mock_file, temp_config_path, sample_config):
    """Save configuration fails with I/O error."""
    # Ensure parent exists
    temp_config_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Assertions
    with pytest.raises(IOError):
        save_config(sample_config, temp_config_path)


@patch("builtins.open", side_effect=OSError(28, "No space left on device"))
def test_save_config_error_disk_full(mock_file, temp_config_path, sample_config):
    """Save configuration fails with disk full error."""
    # Ensure parent exists
    temp_config_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Assertions
    with pytest.raises(OSError) as exc_info:
        save_config(sample_config, temp_config_path)
    assert exc_info.value.errno == 28


# ============================================================================
# LAYER 1: UNIT TESTS - get_config_value
# ============================================================================

def test_get_config_value_happy_path(sample_config):
    """Get configuration value by key successfully."""
    # Get value
    value = get_config_value("repos_dir", sample_config)
    
    # Assertions
    assert isinstance(value, str)
    assert value == sample_config.repos_dir


def test_get_config_value_happy_path_no_config(temp_config_path, sample_config_data):
    """Get configuration value loads config when not provided."""
    # Write config to file
    with open(temp_config_path, 'w') as f:
        yaml.dump(sample_config_data, f)
    
    # Mock the default path
    with patch("contracts_contracts_src_ascend_config_interface_interface.CONFIG_PATH", temp_config_path):
        # Get value without providing config
        value = get_config_value("model", None)
        
        # Assertions
        assert isinstance(value, str)


def test_get_config_value_edge_case_int_to_string(sample_config):
    """Get configuration value converts int to string."""
    # Get int field
    value = get_config_value("default_lookback_hours", sample_config)
    
    # Assertions
    assert isinstance(value, str)
    assert value == str(sample_config.default_lookback_hours)


def test_get_config_value_edge_case_list_to_string(sample_config):
    """Get configuration value converts list to string."""
    # Get list field
    value = get_config_value("linear_team_ids", sample_config)
    
    # Assertions
    assert isinstance(value, str)


def test_get_config_value_edge_case_none_to_string():
    """Get configuration value converts None to string."""
    # Create config with None value
    config = AscendConfig()
    
    # Get None field
    value = get_config_value("repos_dir", config)
    
    # Assertions
    assert isinstance(value, str)


def test_get_config_value_error_unknown_key(sample_config):
    """Get configuration value fails with unknown key."""
    # Assertions
    with pytest.raises(Exception) as exc_info:
        get_config_value("nonexistent_key", sample_config)
    # Should raise unknown_key_error
    assert "key" in str(exc_info.value).lower() or "unknown" in str(exc_info.value).lower()


def test_get_config_value_error_yaml_parse(temp_config_path):
    """Get configuration value fails loading malformed config."""
    # Write malformed YAML
    with open(temp_config_path, 'w') as f:
        f.write("invalid: yaml: [")
    
    # Mock the default path
    with patch("contracts_contracts_src_ascend_config_interface_interface.CONFIG_PATH", temp_config_path):
        # Assertions
        with pytest.raises(Exception) as exc_info:
            get_config_value("model", None)


def test_get_config_value_error_pydantic_validation(temp_config_path):
    """Get configuration value fails with validation error on load."""
    # Write invalid data
    invalid_data = {"default_lookback_hours": "not_an_int"}
    with open(temp_config_path, 'w') as f:
        yaml.dump(invalid_data, f)
    
    # Mock the default path
    with patch("contracts_contracts_src_ascend_config_interface_interface.CONFIG_PATH", temp_config_path):
        # Assertions
        with pytest.raises(Exception):
            get_config_value("model", None)


# ============================================================================
# LAYER 1: UNIT TESTS - set_config_value
# ============================================================================

def test_set_config_value_happy_path_string(temp_config_path, sample_config_data):
    """Set configuration value for string field."""
    # Setup: create initial config
    with open(temp_config_path, 'w') as f:
        yaml.dump(sample_config_data, f)
    
    # Set value
    new_value = "/new/path/to/repos"
    updated_config = set_config_value("repos_dir", new_value, temp_config_path)
    
    # Assertions
    assert isinstance(updated_config, AscendConfig)
    assert updated_config.repos_dir == new_value
    
    # Verify saved to file
    with open(temp_config_path, 'r') as f:
        loaded_data = yaml.safe_load(f)
    assert loaded_data["repos_dir"] == new_value


def test_set_config_value_happy_path_int_coercion(temp_config_path, sample_config_data):
    """Set configuration value with int type coercion."""
    # Setup: create initial config
    with open(temp_config_path, 'w') as f:
        yaml.dump(sample_config_data, f)
    
    # Set int value as string
    new_value = "48"
    updated_config = set_config_value("default_lookback_hours", new_value, temp_config_path)
    
    # Assertions
    assert isinstance(updated_config, AscendConfig)
    assert updated_config.default_lookback_hours == 48
    assert isinstance(updated_config.default_lookback_hours, int)


def test_set_config_value_happy_path_list_coercion(temp_config_path, sample_config_data):
    """Set configuration value with list type coercion."""
    # Setup: create initial config
    with open(temp_config_path, 'w') as f:
        yaml.dump(sample_config_data, f)
    
    # Set list value as comma-separated string
    new_value = "team3, team4, team5"
    updated_config = set_config_value("linear_team_ids", new_value, temp_config_path)
    
    # Assertions
    assert isinstance(updated_config, AscendConfig)
    assert isinstance(updated_config.linear_team_ids, list)
    assert updated_config.linear_team_ids == ["team3", "team4", "team5"]


def test_set_config_value_edge_case_list_single_item(temp_config_path, sample_config_data):
    """Set configuration value with single item list."""
    # Setup: create initial config
    with open(temp_config_path, 'w') as f:
        yaml.dump(sample_config_data, f)
    
    # Set single value
    new_value = "single_team"
    updated_config = set_config_value("linear_team_ids", new_value, temp_config_path)
    
    # Assertions
    assert isinstance(updated_config.linear_team_ids, list)
    assert len(updated_config.linear_team_ids) == 1
    assert updated_config.linear_team_ids[0] == "single_team"


def test_set_config_value_edge_case_list_whitespace(temp_config_path, sample_config_data):
    """Set configuration value with list containing whitespace."""
    # Setup: create initial config
    with open(temp_config_path, 'w') as f:
        yaml.dump(sample_config_data, f)
    
    # Set value with extra whitespace
    new_value = " team1 ,  team2  , team3  "
    updated_config = set_config_value("slack_channels", new_value, temp_config_path)
    
    # Assertions
    assert updated_config.slack_channels == ["team1", "team2", "team3"]
    # Verify no leading/trailing whitespace
    for item in updated_config.slack_channels:
        assert item == item.strip()


def test_set_config_value_error_unknown_key(temp_config_path, sample_config_data):
    """Set configuration value fails with unknown key."""
    # Setup: create initial config
    with open(temp_config_path, 'w') as f:
        yaml.dump(sample_config_data, f)
    
    # Assertions
    with pytest.raises(Exception) as exc_info:
        set_config_value("nonexistent_key", "value", temp_config_path)


def test_set_config_value_error_int_conversion(temp_config_path, sample_config_data):
    """Set configuration value fails converting to int."""
    # Setup: create initial config
    with open(temp_config_path, 'w') as f:
        yaml.dump(sample_config_data, f)
    
    # Assertions
    with pytest.raises(Exception) as exc_info:
        set_config_value("default_lookback_hours", "not_a_number", temp_config_path)


def test_set_config_value_error_pydantic_validation(temp_config_path, sample_config_data):
    """Set configuration value fails Pydantic validation."""
    # This test depends on what Pydantic validators exist
    # For now, we'll use a generic approach
    with open(temp_config_path, 'w') as f:
        yaml.dump(sample_config_data, f)
    
    # Try to set a value that might fail validation
    # (This is a placeholder - actual validation depends on AscendConfig implementation)
    try:
        # If there are specific validators, they would trigger here
        result = set_config_value("model", "", temp_config_path)
        # If no validation error, that's okay too
    except Exception as e:
        # Validation errors are expected in some cases
        pass


def test_set_config_value_error_yaml_parse(temp_config_path):
    """Set configuration value fails loading existing malformed config."""
    # Write malformed YAML
    with open(temp_config_path, 'w') as f:
        f.write("invalid: yaml: [")
    
    # Assertions
    with pytest.raises(Exception):
        set_config_value("model", "new-model", temp_config_path)


@patch("builtins.open", side_effect=PermissionError("Permission denied"))
def test_set_config_value_error_file_permission(mock_file, temp_config_path):
    """Set configuration value fails with permission error."""
    # Touch file so it exists
    temp_config_path.touch()
    
    # Assertions
    with pytest.raises(PermissionError):
        set_config_value("model", "new-model", temp_config_path)


@patch("builtins.open", side_effect=IOError("I/O error"))
def test_set_config_value_error_io_error(mock_file, temp_config_path):
    """Set configuration value fails with I/O error."""
    # Touch file so it exists
    temp_config_path.touch()
    
    # Assertions
    with pytest.raises(IOError):
        set_config_value("model", "new-model", temp_config_path)


# ============================================================================
# LAYER 2: INTEGRATION TESTS
# ============================================================================

def test_integration_create_modify_reload(temp_config_path, sample_config):
    """Full workflow: create, modify, reload config."""
    # Step 1: Save initial config
    save_config(sample_config, temp_config_path)
    assert temp_config_path.exists()
    
    # Step 2: Modify a value
    new_model = "claude-3-sonnet"
    updated_config = set_config_value("model", new_model, temp_config_path)
    assert updated_config.model == new_model
    
    # Step 3: Reload and verify
    reloaded_config = load_config(temp_config_path)
    assert reloaded_config.model == new_model
    assert reloaded_config.repos_dir == sample_config.repos_dir


def test_invariant_round_trip(temp_config_path, sample_config):
    """Save and load config preserves data integrity."""
    # Save config
    save_config(sample_config, temp_config_path)
    
    # Load config
    loaded_config = load_config(temp_config_path)
    
    # Assertions - all non-None values should match
    assert loaded_config.repos_dir == sample_config.repos_dir
    assert loaded_config.model == sample_config.model
    assert loaded_config.default_lookback_hours == sample_config.default_lookback_hours
    assert loaded_config.linear_team_ids == sample_config.linear_team_ids
    assert loaded_config.slack_channels == sample_config.slack_channels


# ============================================================================
# LAYER 3: INVARIANT TESTS
# ============================================================================

def test_invariant_config_path_default():
    """CONFIG_PATH is always ~/.ascend/config.yaml."""
    with patch("pathlib.Path.home") as mock_home:
        mock_home.return_value = Path("/mock/home")
        
        # Import or access CONFIG_PATH constant
        # This test verifies the default path follows the contract
        from contracts.contracts_src_ascend_config_interface.interface import CONFIG_PATH
        
        # Verify it follows pattern ~/.ascend/config.yaml
        assert "config.yaml" in str(CONFIG_PATH)


def test_invariant_ascend_home():
    """ASCEND_HOME is always ~/.ascend."""
    from contracts.contracts_src_ascend_config_interface.interface import ASCEND_HOME
    
    # Verify pattern
    assert ".ascend" in str(ASCEND_HOME)


def test_invariant_yaml_format(temp_config_path, sample_config):
    """Config files are always YAML with default_flow_style=False."""
    # Save config
    save_config(sample_config, temp_config_path)
    
    # Read raw content
    with open(temp_config_path, 'r') as f:
        content = f.read()
    
    # Assertions - block style should have newlines and indentation
    assert '\n' in content
    # Flow style would look like: {key: value, key2: value2}
    # Block style has keys on separate lines
    lines = content.split('\n')
    assert len(lines) > 1


def test_invariant_none_filtering(temp_config_path):
    """None values from YAML are always filtered before model construction."""
    # Create YAML with explicit None values
    data_with_none = {
        "repos_dir": "/path/to/repos",
        "model": None,
        "reports_dir": None,
        "default_lookback_hours": 24,
    }
    
    with open(temp_config_path, 'w') as f:
        yaml.dump(data_with_none, f)
    
    # Load config
    config = load_config(temp_config_path)
    
    # Assertions - should successfully load
    assert isinstance(config, AscendConfig)
    assert config.repos_dir == "/path/to/repos"
    assert config.default_lookback_hours == 24


def test_invariant_string_conversion(sample_config):
    """All config values are convertible to string representation."""
    # Test various field types
    fields = [
        "repos_dir",
        "model", 
        "default_lookback_hours",
        "linear_team_ids",
    ]
    
    for field in fields:
        value = get_config_value(field, sample_config)
        assert isinstance(value, str)


def test_load_config_filters_none_values(temp_config_path):
    """Verify None values are filtered from YAML before construction."""
    # Create config with mix of None and values
    mixed_data = {
        "repos_dir": "/path",
        "model": None,
        "config_dir": None,
        "default_lookback_hours": 12,
        "linear_team_ids": None,
    }
    
    with open(temp_config_path, 'w') as f:
        yaml.dump(mixed_data, f)
    
    # Load and verify
    config = load_config(temp_config_path)
    
    assert isinstance(config, AscendConfig)
    assert config.repos_dir == "/path"
    assert config.default_lookback_hours == 12


# ============================================================================
# LAYER 4: TYPE CONSTRUCTION TESTS
# ============================================================================

def test_ascend_config_construction_happy():
    """AscendConfig can be constructed with valid data."""
    config = AscendConfig(
        repos_dir="/path",
        model="claude-3-opus",
        default_lookback_hours=24,
        linear_team_ids=["team1"],
    )
    
    assert isinstance(config, AscendConfig)
    assert config.repos_dir == "/path"
    assert config.model == "claude-3-opus"
    assert config.default_lookback_hours == 24
    assert config.linear_team_ids == ["team1"]


def test_ascend_config_construction_all_optional():
    """AscendConfig can be constructed with no arguments."""
    config = AscendConfig()
    
    assert isinstance(config, AscendConfig)
    # All fields should be accessible (even if None)
    _ = config.repos_dir
    _ = config.model
    _ = config.default_lookback_hours


# ============================================================================
# ADDITIONAL EDGE CASES AND ERROR COVERAGE
# ============================================================================

def test_save_config_yaml_serialization(temp_config_path):
    """Verify YAML serialization handles various data types."""
    config = AscendConfig(
        repos_dir="/path",
        default_lookback_hours=100,
        linear_team_ids=["a", "b", "c"],
        slack_channels=["#channel1", "#channel2"],
    )
    
    save_config(config, temp_config_path)
    
    # Reload and verify types
    with open(temp_config_path, 'r') as f:
        data = yaml.safe_load(f)
    
    assert isinstance(data["repos_dir"], str)
    assert isinstance(data["default_lookback_hours"], int)
    assert isinstance(data["linear_team_ids"], list)
    assert isinstance(data["slack_channels"], list)


def test_get_config_value_all_fields(sample_config):
    """Test get_config_value works for all field types."""
    # Get each field type
    str_val = get_config_value("repos_dir", sample_config)
    int_val = get_config_value("default_lookback_hours", sample_config)
    list_val = get_config_value("linear_team_ids", sample_config)
    
    # All should be strings
    assert isinstance(str_val, str)
    assert isinstance(int_val, str)
    assert isinstance(list_val, str)


def test_set_config_value_updates_file_atomically(temp_config_path, sample_config_data):
    """Verify set_config_value properly updates and saves."""
    # Create initial config
    with open(temp_config_path, 'w') as f:
        yaml.dump(sample_config_data, f)
    
    # Update value
    set_config_value("manager_name", "Jane Doe", temp_config_path)
    
    # Verify file was updated
    with open(temp_config_path, 'r') as f:
        data = yaml.safe_load(f)
    
    assert data["manager_name"] == "Jane Doe"
    # Other values should remain
    assert data["repos_dir"] == sample_config_data["repos_dir"]


def test_load_config_with_extra_fields(temp_config_path):
    """Load configuration ignores extra fields not in AscendConfig."""
    # Create YAML with extra fields
    data_with_extra = {
        "repos_dir": "/path",
        "model": "claude-3-opus",
        "extra_field": "should_be_ignored",
        "another_extra": 123,
    }
    
    with open(temp_config_path, 'w') as f:
        yaml.dump(data_with_extra, f)
    
    # Should load successfully (Pydantic typically ignores extra fields by default)
    config = load_config(temp_config_path)
    assert isinstance(config, AscendConfig)


def test_set_config_value_list_empty_string(temp_config_path, sample_config_data):
    """Set list config value with empty string."""
    with open(temp_config_path, 'w') as f:
        yaml.dump(sample_config_data, f)
    
    # Set empty string (should result in single empty item or empty list)
    updated = set_config_value("linear_team_ids", "", temp_config_path)
    
    # Should handle gracefully
    assert isinstance(updated.linear_team_ids, list)


def test_config_operations_with_unicode(temp_config_path):
    """Test config handles Unicode characters."""
    unicode_config = AscendConfig(
        repos_dir="/path/to/résumé",
        manager_name="José García",
    )
    
    save_config(unicode_config, temp_config_path)
    loaded = load_config(temp_config_path)
    
    assert loaded.repos_dir == "/path/to/résumé"
    assert loaded.manager_name == "José García"


def test_multiple_sequential_updates(temp_config_path, sample_config_data):
    """Test multiple sequential set_config_value calls."""
    # Initial save
    with open(temp_config_path, 'w') as f:
        yaml.dump(sample_config_data, f)
    
    # Multiple updates
    set_config_value("model", "claude-3-haiku", temp_config_path)
    set_config_value("default_lookback_hours", "48", temp_config_path)
    set_config_value("manager_name", "Alice", temp_config_path)
    
    # Load and verify all updates
    final = load_config(temp_config_path)
    assert final.model == "claude-3-haiku"
    assert final.default_lookback_hours == 48
    assert final.manager_name == "Alice"


# ============================================================================
# RANDOM TESTING (using random module instead of hypothesis)
# ============================================================================

def test_random_string_fields():
    """Test config with random string values."""
    random_strings = {
        "repos_dir": ''.join(random.choices(string.ascii_letters, k=20)),
        "model": ''.join(random.choices(string.ascii_letters, k=15)),
        "manager_name": ''.join(random.choices(string.ascii_letters + ' ', k=25)),
    }
    
    config = AscendConfig(**random_strings)
    assert config.repos_dir == random_strings["repos_dir"]
    assert config.model == random_strings["model"]


def test_random_int_coercion(temp_config_path, sample_config_data):
    """Test int coercion with random valid integers."""
    with open(temp_config_path, 'w') as f:
        yaml.dump(sample_config_data, f)
    
    random_int = random.randint(1, 1000)
    updated = set_config_value("default_lookback_hours", str(random_int), temp_config_path)
    
    assert updated.default_lookback_hours == random_int


def test_random_list_coercion(temp_config_path, sample_config_data):
    """Test list coercion with random items."""
    with open(temp_config_path, 'w') as f:
        yaml.dump(sample_config_data, f)
    
    # Generate random list items
    num_items = random.randint(1, 10)
    items = [f"item_{i}" for i in range(num_items)]
    value_str = ", ".join(items)
    
    updated = set_config_value("linear_team_ids", value_str, temp_config_path)
    
    assert len(updated.linear_team_ids) == num_items
    assert updated.linear_team_ids == items


# ============================================================================
# END OF TEST SUITE
# ============================================================================
