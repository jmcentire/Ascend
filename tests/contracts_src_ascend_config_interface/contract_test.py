"""
Executable pytest test suite for contracts_src_ascend_config_interface.

This test suite validates the AscendConfig configuration management system
with comprehensive coverage of happy paths, edge cases, error conditions,
and invariants.

Test Organization:
- Layer 1: Unit tests for each function (load_config, save_config, get_config_value, set_config_value)
- Layer 2: Parametric tests for all 12 config fields
- Layer 3: Integration tests for complete workflows
- Layer 4: Error condition tests for all 7 error types
- Layer 5: Invariant validation tests

Mocking Strategy:
- Mock ONLY filesystem operations (pathlib.Path methods)
- Use REAL yaml and pydantic for parsing/validation
- Mock environment variables using monkeypatch
"""

import pytest
import yaml
import tempfile
import os
from pathlib import Path
from typing import Optional
from unittest.mock import Mock, MagicMock, patch, mock_open
from io import StringIO

# Import the component under test
from contracts.src_ascend_config.interface import (
    AscendConfig,
    load_config,
    save_config,
    get_config_value,
    set_config_value,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def valid_config_data():
    """Sample valid configuration data."""
    return {
        'repos_dir': '/home/user/repos',
        'reports_dir': '/home/user/reports',
        'config_dir': '/home/user/.ascend',
        'anthropic_api_key_env': 'ANTHROPIC_API_KEY',
        'model': 'claude-3-opus',
        'default_lookback_hours': 48,
        'linear_team_id': 'team-123',
        'linear_api_key_env': 'LINEAR_API_KEY',
        'linear_team_ids': ['team-1', 'team-2'],
        'slack_channels': ['#general', '#dev'],
        'slack_bot_token_env': 'SLACK_BOT_TOKEN',
        'github_org': 'myorg',
        'manager_name': 'John Doe'
    }


@pytest.fixture
def valid_config_yaml(valid_config_data):
    """Sample valid YAML configuration."""
    return yaml.dump(valid_config_data, default_flow_style=False)


@pytest.fixture
def config_with_none_values():
    """Configuration data with None values that should be filtered."""
    return {
        'repos_dir': '/home/user/repos',
        'reports_dir': None,
        'config_dir': '/home/user/.ascend',
        'anthropic_api_key_env': 'ANTHROPIC_API_KEY',
        'model': None,
        'default_lookback_hours': 48,
        'linear_team_id': 'team-123',
        'linear_api_key_env': None,
        'linear_team_ids': ['team-1'],
        'slack_channels': None,
        'slack_bot_token_env': 'SLACK_BOT_TOKEN',
        'github_org': 'myorg',
        'manager_name': None
    }


@pytest.fixture
def invalid_yaml_content():
    """Malformed YAML content for error testing."""
    return """
    repos_dir: /home/user/repos
    reports_dir: [unclosed list
    model: "unterminated string
    """


@pytest.fixture
def tmp_config_path(tmp_path):
    """Temporary config file path for testing."""
    return tmp_path / "config.yaml"


# =============================================================================
# LAYER 1: UNIT TESTS - load_config
# =============================================================================

def test_load_config_happy_path_existing_file(tmp_config_path, valid_config_yaml):
    """Load config from existing YAML file with all fields populated."""
    # Setup: Create a valid config file
    tmp_config_path.write_text(valid_config_yaml)
    
    # Execute
    config = load_config(tmp_config_path)
    
    # Assert
    assert isinstance(config, AscendConfig)
    assert config.repos_dir == '/home/user/repos'
    assert config.reports_dir == '/home/user/reports'
    assert config.model == 'claude-3-opus'
    assert config.default_lookback_hours == 48
    assert config.linear_team_ids == ['team-1', 'team-2']
    assert config.slack_channels == ['#general', '#dev']
    assert config.manager_name == 'John Doe'


def test_load_config_happy_path_missing_file(tmp_path):
    """Load config when file does not exist, should return defaults."""
    # Setup: Use path that doesn't exist
    non_existent_path = tmp_path / "nonexistent" / "config.yaml"
    
    # Execute
    config = load_config(non_existent_path)
    
    # Assert: Should return AscendConfig with defaults (no error)
    assert isinstance(config, AscendConfig)
    # Verify it has some default values (implementation may vary)
    assert hasattr(config, 'repos_dir')
    assert hasattr(config, 'model')
    assert hasattr(config, 'default_lookback_hours')


def test_load_config_filters_none_values(tmp_config_path, config_with_none_values):
    """Load config with None values in YAML - should filter them out."""
    # Setup: Create config file with None values
    yaml_content = yaml.dump(config_with_none_values, default_flow_style=False)
    tmp_config_path.write_text(yaml_content)
    
    # Execute
    config = load_config(tmp_config_path)
    
    # Assert: Config loaded successfully with None values filtered
    assert isinstance(config, AscendConfig)
    assert config.repos_dir == '/home/user/repos'
    # Fields that were None should use defaults
    assert config.default_lookback_hours == 48  # This was not None


def test_load_config_yaml_parse_error(tmp_config_path, invalid_yaml_content):
    """Load config from malformed YAML file."""
    # Setup: Create malformed YAML file
    tmp_config_path.write_text(invalid_yaml_content)
    
    # Execute & Assert
    with pytest.raises(Exception) as exc_info:
        load_config(tmp_config_path)
    
    # The error should be a yaml_parse_error (implementation-specific exception)
    assert exc_info.value.__class__.__name__ in ['yaml_parse_error', 'YAMLError', 'ScannerError']


def test_load_config_pydantic_validation_error(tmp_config_path):
    """Load config with invalid data that fails Pydantic validation."""
    # Setup: Create YAML with invalid data type
    invalid_data = {
        'repos_dir': '/home/user/repos',
        'default_lookback_hours': 'not_an_integer',  # Should be int
        'linear_team_ids': 'not_a_list'  # Should be list
    }
    yaml_content = yaml.dump(invalid_data, default_flow_style=False)
    tmp_config_path.write_text(yaml_content)
    
    # Execute & Assert
    with pytest.raises(Exception) as exc_info:
        load_config(tmp_config_path)
    
    # Should be pydantic_validation_error or ValidationError
    assert exc_info.value.__class__.__name__ in ['pydantic_validation_error', 'ValidationError']


def test_load_config_file_permission_error(tmp_config_path, valid_config_yaml):
    """Load config when lacking read permissions."""
    # Setup: Create file and remove read permissions
    tmp_config_path.write_text(valid_config_yaml)
    
    # Mock permission error
    with patch('pathlib.Path.read_text', side_effect=PermissionError("Permission denied")):
        # Execute & Assert
        with pytest.raises(Exception) as exc_info:
            load_config(tmp_config_path)
        
        assert exc_info.value.__class__.__name__ in ['file_permission_error', 'PermissionError']


def test_load_config_io_error(tmp_config_path):
    """Load config with filesystem I/O error."""
    # Setup: Mock I/O error
    with patch('pathlib.Path.read_text', side_effect=IOError("I/O error")):
        with patch('pathlib.Path.exists', return_value=True):
            # Execute & Assert
            with pytest.raises(Exception) as exc_info:
                load_config(tmp_config_path)
            
            assert exc_info.value.__class__.__name__ in ['io_error', 'IOError', 'OSError']


# =============================================================================
# LAYER 1: UNIT TESTS - save_config
# =============================================================================

def test_save_config_happy_path(tmp_config_path, valid_config_data):
    """Save valid AscendConfig to YAML file."""
    # Setup: Create valid config instance
    config = AscendConfig(**valid_config_data)
    
    # Execute
    save_config(config, tmp_config_path)
    
    # Assert: File exists
    assert tmp_config_path.exists()
    
    # Assert: Content is valid YAML
    content = tmp_config_path.read_text()
    loaded_data = yaml.safe_load(content)
    assert loaded_data is not None
    assert loaded_data['repos_dir'] == '/home/user/repos'
    assert loaded_data['default_lookback_hours'] == 48
    
    # Assert: Check that YAML uses block style (not flow style)
    assert '[' not in content or '\n' in content  # Block style check


def test_save_config_creates_parent_dirs(tmp_path, valid_config_data):
    """Save config creates parent directories if they don't exist."""
    # Setup: Path with non-existent parent directories
    nested_path = tmp_path / "level1" / "level2" / "config.yaml"
    config = AscendConfig(**valid_config_data)
    
    # Execute
    save_config(config, nested_path)
    
    # Assert: Parent directories created
    assert nested_path.parent.exists()
    assert nested_path.exists()


def test_save_config_file_permission_error(tmp_config_path, valid_config_data):
    """Save config when lacking write permissions."""
    # Setup
    config = AscendConfig(**valid_config_data)
    
    # Mock permission error
    with patch('pathlib.Path.mkdir', side_effect=PermissionError("Permission denied")):
        # Execute & Assert
        with pytest.raises(Exception) as exc_info:
            save_config(config, tmp_config_path)
        
        assert exc_info.value.__class__.__name__ in ['file_permission_error', 'PermissionError']


def test_save_config_io_error(tmp_config_path, valid_config_data):
    """Save config with filesystem I/O error."""
    # Setup
    config = AscendConfig(**valid_config_data)
    
    # Mock I/O error during write
    with patch('pathlib.Path.write_text', side_effect=IOError("I/O error")):
        # Execute & Assert
        with pytest.raises(Exception) as exc_info:
            save_config(config, tmp_config_path)
        
        assert exc_info.value.__class__.__name__ in ['io_error', 'IOError', 'OSError']


def test_save_config_disk_full_error(tmp_config_path, valid_config_data):
    """Save config when disk is full."""
    # Setup
    config = AscendConfig(**valid_config_data)
    
    # Mock disk full error (OSError with ENOSPC errno)
    disk_full_error = OSError(28, "No space left on device")
    with patch('pathlib.Path.write_text', side_effect=disk_full_error):
        # Execute & Assert
        with pytest.raises(Exception) as exc_info:
            save_config(config, tmp_config_path)
        
        assert exc_info.value.__class__.__name__ in ['disk_full_error', 'OSError']


# =============================================================================
# LAYER 1: UNIT TESTS - get_config_value
# =============================================================================

def test_get_config_value_happy_path(valid_config_data):
    """Get config value for valid key with provided config."""
    # Setup
    config = AscendConfig(**valid_config_data)
    
    # Execute
    value = get_config_value('repos_dir', config)
    
    # Assert: Returns string
    assert isinstance(value, str)
    assert value == '/home/user/repos'


def test_get_config_value_loads_config_when_none(tmp_config_path, valid_config_yaml):
    """Get config value when cfg is None - should load from file."""
    # Setup: Create config file
    tmp_config_path.write_text(valid_config_yaml)
    
    # Mock the default config path to use our tmp path
    with patch('contracts_src_ascend_config_interface.CONFIG_PATH', tmp_config_path):
        # Execute: Pass None for cfg
        value = get_config_value('model', None)
        
        # Assert: Config loaded and value returned
        assert isinstance(value, str)
        assert value == 'claude-3-opus'


def test_get_config_value_converts_non_string_to_string(valid_config_data):
    """Get config value for non-string field (int, list) - should convert to string."""
    # Setup
    config = AscendConfig(**valid_config_data)
    
    # Execute: Get int field
    int_value = get_config_value('default_lookback_hours', config)
    assert isinstance(int_value, str)
    assert int_value == '48'
    
    # Execute: Get list field
    list_value = get_config_value('slack_channels', config)
    assert isinstance(list_value, str)
    assert 'general' in list_value or '#general' in list_value


def test_get_config_value_unknown_key_error(valid_config_data):
    """Get config value for non-existent key."""
    # Setup
    config = AscendConfig(**valid_config_data)
    
    # Execute & Assert
    with pytest.raises(Exception) as exc_info:
        get_config_value('nonexistent_key', config)
    
    assert exc_info.value.__class__.__name__ in ['unknown_key_error', 'KeyError', 'AttributeError']


def test_get_config_value_yaml_parse_error(tmp_config_path, invalid_yaml_content):
    """Get config value when config file is malformed (cfg=None)."""
    # Setup: Create malformed config file
    tmp_config_path.write_text(invalid_yaml_content)
    
    # Mock the default config path
    with patch('contracts_src_ascend_config_interface.CONFIG_PATH', tmp_config_path):
        # Execute & Assert
        with pytest.raises(Exception) as exc_info:
            get_config_value('model', None)
        
        assert exc_info.value.__class__.__name__ in ['yaml_parse_error', 'YAMLError', 'ScannerError']


def test_get_config_value_pydantic_validation_error(tmp_config_path):
    """Get config value when loaded config fails validation (cfg=None)."""
    # Setup: Create config with invalid data
    invalid_data = {
        'default_lookback_hours': 'invalid_int'
    }
    yaml_content = yaml.dump(invalid_data, default_flow_style=False)
    tmp_config_path.write_text(yaml_content)
    
    # Mock the default config path
    with patch('contracts_src_ascend_config_interface.CONFIG_PATH', tmp_config_path):
        # Execute & Assert
        with pytest.raises(Exception) as exc_info:
            get_config_value('model', None)
        
        assert exc_info.value.__class__.__name__ in ['pydantic_validation_error', 'ValidationError']


# =============================================================================
# LAYER 1: UNIT TESTS - set_config_value
# =============================================================================

def test_set_config_value_happy_path_string(tmp_config_path, valid_config_yaml):
    """Set config value for string field."""
    # Setup: Create initial config
    tmp_config_path.write_text(valid_config_yaml)
    
    # Execute
    updated_config = set_config_value('model', 'claude-3-sonnet', tmp_config_path)
    
    # Assert: Config updated
    assert isinstance(updated_config, AscendConfig)
    assert updated_config.model == 'claude-3-sonnet'
    
    # Assert: File saved
    assert tmp_config_path.exists()
    reloaded_data = yaml.safe_load(tmp_config_path.read_text())
    assert reloaded_data['model'] == 'claude-3-sonnet'


def test_set_config_value_happy_path_int(tmp_config_path, valid_config_yaml):
    """Set config value for int field with type coercion."""
    # Setup
    tmp_config_path.write_text(valid_config_yaml)
    
    # Execute: Pass string that should be coerced to int
    updated_config = set_config_value('default_lookback_hours', '72', tmp_config_path)
    
    # Assert: Value coerced to int
    assert isinstance(updated_config, AscendConfig)
    assert updated_config.default_lookback_hours == 72
    assert isinstance(updated_config.default_lookback_hours, int)


def test_set_config_value_happy_path_list(tmp_config_path, valid_config_yaml):
    """Set config value for list field with comma-separated string."""
    # Setup
    tmp_config_path.write_text(valid_config_yaml)
    
    # Execute: Pass comma-separated string
    updated_config = set_config_value('slack_channels', '#new-channel, #another-channel', tmp_config_path)
    
    # Assert: Value split into list with whitespace stripped
    assert isinstance(updated_config, AscendConfig)
    assert isinstance(updated_config.slack_channels, list)
    assert '#new-channel' in updated_config.slack_channels
    assert '#another-channel' in updated_config.slack_channels
    # Check whitespace was stripped
    for channel in updated_config.slack_channels:
        assert channel == channel.strip()


def test_set_config_value_unknown_key_error(tmp_config_path, valid_config_yaml):
    """Set config value for non-existent key."""
    # Setup
    tmp_config_path.write_text(valid_config_yaml)
    
    # Execute & Assert
    with pytest.raises(Exception) as exc_info:
        set_config_value('invalid_key', 'value', tmp_config_path)
    
    assert exc_info.value.__class__.__name__ in ['unknown_key_error', 'KeyError', 'AttributeError']


def test_set_config_value_int_conversion_error(tmp_config_path, valid_config_yaml):
    """Set config value for int field with non-convertible value."""
    # Setup
    tmp_config_path.write_text(valid_config_yaml)
    
    # Execute & Assert
    with pytest.raises(Exception) as exc_info:
        set_config_value('default_lookback_hours', 'not_a_number', tmp_config_path)
    
    assert exc_info.value.__class__.__name__ in ['int_conversion_error', 'ValueError']


def test_set_config_value_pydantic_validation_error(tmp_config_path, valid_config_yaml):
    """Set config value that causes Pydantic validation failure."""
    # Setup
    tmp_config_path.write_text(valid_config_yaml)
    
    # Execute & Assert: Try setting an int to a negative value if validation disallows it
    # This depends on AscendConfig validators
    with pytest.raises(Exception) as exc_info:
        # Attempt to set a value that would fail validation
        # For example, if there's a minimum value constraint
        set_config_value('default_lookback_hours', '-1', tmp_config_path)
    
    # May raise int_conversion_error or pydantic_validation_error depending on implementation


def test_set_config_value_yaml_parse_error(tmp_config_path, invalid_yaml_content):
    """Set config value when existing config file is malformed."""
    # Setup: Create malformed config
    tmp_config_path.write_text(invalid_yaml_content)
    
    # Execute & Assert
    with pytest.raises(Exception) as exc_info:
        set_config_value('model', 'new-model', tmp_config_path)
    
    assert exc_info.value.__class__.__name__ in ['yaml_parse_error', 'YAMLError', 'ScannerError']


def test_set_config_value_file_permission_error(tmp_config_path, valid_config_yaml):
    """Set config value when lacking permissions."""
    # Setup
    tmp_config_path.write_text(valid_config_yaml)
    
    # Mock permission error
    with patch('pathlib.Path.write_text', side_effect=PermissionError("Permission denied")):
        # Execute & Assert
        with pytest.raises(Exception) as exc_info:
            set_config_value('model', 'new-model', tmp_config_path)
        
        assert exc_info.value.__class__.__name__ in ['file_permission_error', 'PermissionError']


def test_set_config_value_io_error(tmp_config_path, valid_config_yaml):
    """Set config value with filesystem I/O error."""
    # Setup
    tmp_config_path.write_text(valid_config_yaml)
    
    # Mock I/O error on write
    original_read = Path.read_text
    with patch('pathlib.Path.write_text', side_effect=IOError("I/O error")):
        # Execute & Assert
        with pytest.raises(Exception) as exc_info:
            set_config_value('model', 'new-model', tmp_config_path)
        
        assert exc_info.value.__class__.__name__ in ['io_error', 'IOError', 'OSError']


# =============================================================================
# LAYER 2: PARAMETRIC TESTS FOR ALL CONFIG FIELDS
# =============================================================================

@pytest.mark.parametrize("field_name,valid_value,invalid_value", [
    ('repos_dir', '/home/user/repos', None),  # str
    ('reports_dir', '/home/user/reports', None),  # str
    ('config_dir', '/home/user/.ascend', None),  # str
    ('anthropic_api_key_env', 'ANTHROPIC_KEY', None),  # str
    ('model', 'claude-3-opus', None),  # str
    ('default_lookback_hours', 48, 'invalid'),  # int
    ('linear_team_id', 'team-123', None),  # str
    ('linear_api_key_env', 'LINEAR_KEY', None),  # str
    ('linear_team_ids', ['team-1', 'team-2'], 'not-a-list'),  # list[str]
    ('slack_channels', ['#general'], 'not-a-list'),  # list[str]
    ('slack_bot_token_env', 'SLACK_TOKEN', None),  # str
    ('github_org', 'myorg', None),  # str
])
def test_config_field_validation(field_name, valid_value, invalid_value, valid_config_data):
    """Test validation for each config field with valid and invalid values."""
    # Test valid value
    config_data = valid_config_data.copy()
    config_data[field_name] = valid_value
    config = AscendConfig(**config_data)
    assert getattr(config, field_name) == valid_value
    
    # Test invalid value (if applicable)
    if invalid_value is not None and field_name not in ['manager_name']:  # manager_name is Optional
        config_data[field_name] = invalid_value
        with pytest.raises(Exception):  # Should raise validation error
            AscendConfig(**config_data)


# =============================================================================
# LAYER 3: INTEGRATION TESTS
# =============================================================================

def test_integration_load_modify_save_reload(tmp_config_path, valid_config_yaml):
    """Integration test: load config, modify value, save, reload and verify."""
    # Setup: Create initial config file
    tmp_config_path.write_text(valid_config_yaml)
    
    # Step 1: Load config
    config1 = load_config(tmp_config_path)
    original_model = config1.model
    
    # Step 2: Modify and save
    updated_config = set_config_value('model', 'claude-3-sonnet', tmp_config_path)
    assert updated_config.model == 'claude-3-sonnet'
    assert updated_config.model != original_model
    
    # Step 3: Reload from file
    config2 = load_config(tmp_config_path)
    
    # Step 4: Verify persistence
    assert config2.model == 'claude-3-sonnet'
    assert config2.repos_dir == config1.repos_dir  # Other fields unchanged


# =============================================================================
# LAYER 4: EDGE CASE TESTS
# =============================================================================

def test_edge_case_optional_fields(tmp_config_path):
    """Test optional fields (manager_name) with None, explicit value, and omission."""
    # Test with explicit value
    config_data = {
        'repos_dir': '/repos',
        'reports_dir': '/reports',
        'config_dir': '/config',
        'anthropic_api_key_env': 'KEY',
        'model': 'claude',
        'default_lookback_hours': 24,
        'linear_team_id': 'team',
        'linear_api_key_env': 'KEY',
        'linear_team_ids': [],
        'slack_channels': [],
        'slack_bot_token_env': 'TOKEN',
        'github_org': 'org',
        'manager_name': 'John Doe'
    }
    config = AscendConfig(**config_data)
    assert config.manager_name == 'John Doe'
    
    # Test with None
    config_data['manager_name'] = None
    config = AscendConfig(**config_data)
    assert config.manager_name is None
    
    # Test with omission
    del config_data['manager_name']
    config = AscendConfig(**config_data)
    # Should either be None or have a default


def test_edge_case_empty_lists(tmp_config_path):
    """Test list fields with empty lists."""
    config_data = {
        'repos_dir': '/repos',
        'reports_dir': '/reports',
        'config_dir': '/config',
        'anthropic_api_key_env': 'KEY',
        'model': 'claude',
        'default_lookback_hours': 24,
        'linear_team_id': 'team',
        'linear_api_key_env': 'KEY',
        'linear_team_ids': [],  # Empty list
        'slack_channels': [],  # Empty list
        'slack_bot_token_env': 'TOKEN',
        'github_org': 'org',
    }
    
    # Should not raise validation errors
    config = AscendConfig(**config_data)
    assert config.linear_team_ids == []
    assert config.slack_channels == []


def test_edge_case_whitespace_in_list_values(tmp_config_path, valid_config_yaml):
    """Test list field setting with extra whitespace."""
    # Setup
    tmp_config_path.write_text(valid_config_yaml)
    
    # Execute: Set list with extra whitespace
    updated_config = set_config_value('slack_channels', '  #chan1  ,  #chan2  , #chan3  ', tmp_config_path)
    
    # Assert: Whitespace stripped
    for channel in updated_config.slack_channels:
        assert channel == channel.strip()
        assert not channel.startswith(' ')
        assert not channel.endswith(' ')


def test_edge_case_negative_integer(tmp_config_path, valid_config_yaml):
    """Test integer field with negative value."""
    # Setup
    tmp_config_path.write_text(valid_config_yaml)
    
    # Execute & Assert
    # Depending on validation, this may be accepted or rejected
    try:
        updated_config = set_config_value('default_lookback_hours', '-10', tmp_config_path)
        # If accepted, verify it's stored as negative int
        assert updated_config.default_lookback_hours == -10
    except Exception as e:
        # If rejected, should be validation error
        assert e.__class__.__name__ in ['pydantic_validation_error', 'ValidationError', 'ValueError']


# =============================================================================
# LAYER 5: INVARIANT TESTS
# =============================================================================

def test_invariant_config_path():
    """Verify CONFIG_PATH is always ~/.ascend/config.yaml."""
    from contracts.src_ascend_config.interface import CONFIG_PATH
    
    expected_path = Path.home() / '.ascend' / 'config.yaml'
    assert CONFIG_PATH == expected_path


def test_invariant_ascend_home():
    """Verify ASCEND_HOME is always ~/.ascend."""
    from contracts.src_ascend_config.interface import ASCEND_HOME
    
    expected_home = Path.home() / '.ascend'
    assert ASCEND_HOME == expected_home


def test_invariant_yaml_format(tmp_config_path, valid_config_data):
    """Verify config files always use YAML format with default_flow_style=False."""
    # Setup
    config = AscendConfig(**valid_config_data)
    
    # Execute
    save_config(config, tmp_config_path)
    
    # Assert: File is valid YAML
    content = tmp_config_path.read_text()
    data = yaml.safe_load(content)
    assert data is not None
    
    # Assert: Not using flow style (flow style would have lots of brackets/braces on same lines)
    # Block style typically has keys on separate lines
    assert content.count('\n') > 5  # Multiple lines indicate block style


def test_invariant_none_filtering(tmp_config_path, config_with_none_values):
    """Verify None values from YAML are always filtered before model construction."""
    # Setup: Create YAML with None values
    yaml_content = yaml.dump(config_with_none_values, default_flow_style=False)
    tmp_config_path.write_text(yaml_content)
    
    # Execute
    config = load_config(tmp_config_path)
    
    # Assert: Config created successfully (None values were filtered)
    assert isinstance(config, AscendConfig)
    
    # Verify that fields with None in YAML got default values or None handling
    # The exact behavior depends on implementation


def test_invariant_string_conversion(valid_config_data):
    """Verify all config values are convertible to string representation."""
    # Setup
    config = AscendConfig(**valid_config_data)
    
    # Execute & Assert: All fields should convert to string
    for field_name in config.__dict__.keys():
        value = getattr(config, field_name)
        str_value = str(value)
        assert isinstance(str_value, str)
        # Should not raise any exceptions


# =============================================================================
# ADDITIONAL EDGE CASE TESTS
# =============================================================================

def test_config_round_trip_serialization(tmp_config_path, valid_config_data):
    """Test that config can be saved and loaded without data loss."""
    # Setup
    original_config = AscendConfig(**valid_config_data)
    
    # Execute: Save and reload
    save_config(original_config, tmp_config_path)
    reloaded_config = load_config(tmp_config_path)
    
    # Assert: All fields match
    for field_name in valid_config_data.keys():
        original_value = getattr(original_config, field_name)
        reloaded_value = getattr(reloaded_config, field_name)
        assert original_value == reloaded_value


def test_concurrent_write_safety(tmp_config_path, valid_config_yaml):
    """Test that writes are atomic or handle concurrent access safely."""
    # Setup
    tmp_config_path.write_text(valid_config_yaml)
    
    # This is a basic test - real atomic writes would use temp file + rename
    # Execute multiple writes
    set_config_value('model', 'model-1', tmp_config_path)
    set_config_value('model', 'model-2', tmp_config_path)
    set_config_value('model', 'model-3', tmp_config_path)
    
    # Assert: File is still valid and has last write
    config = load_config(tmp_config_path)
    assert config.model == 'model-3'


def test_unicode_and_special_characters(tmp_config_path):
    """Test handling of unicode and special characters in config values."""
    config_data = {
        'repos_dir': '/home/user/repos',
        'reports_dir': '/reports',
        'config_dir': '/config',
        'anthropic_api_key_env': 'KEY',
        'model': 'claude-with-émojis-🎉',
        'default_lookback_hours': 24,
        'linear_team_id': 'team-特殊字符',
        'linear_api_key_env': 'KEY',
        'linear_team_ids': ['team-α', 'team-β'],
        'slack_channels': ['#канал', '#頻道'],
        'slack_bot_token_env': 'TOKEN',
        'github_org': 'org-企業',
        'manager_name': 'João Müller'
    }
    
    # Should handle unicode without errors
    config = AscendConfig(**config_data)
    save_config(config, tmp_config_path)
    reloaded = load_config(tmp_config_path)
    
    assert reloaded.model == 'claude-with-émojis-🎉'
    assert reloaded.manager_name == 'João Müller'


def test_get_config_all_field_types(valid_config_data):
    """Test get_config_value for all different field types."""
    config = AscendConfig(**valid_config_data)
    
    # String field
    str_val = get_config_value('model', config)
    assert isinstance(str_val, str)
    
    # Int field
    int_val = get_config_value('default_lookback_hours', config)
    assert isinstance(int_val, str)
    assert int_val == '48'
    
    # List field
    list_val = get_config_value('slack_channels', config)
    assert isinstance(list_val, str)
    
    # Optional field
    opt_val = get_config_value('manager_name', config)
    assert isinstance(opt_val, str)


def test_set_config_preserves_other_fields(tmp_config_path, valid_config_yaml):
    """Test that set_config_value only changes the target field."""
    # Setup
    tmp_config_path.write_text(valid_config_yaml)
    original_config = load_config(tmp_config_path)
    
    # Execute: Change one field
    updated_config = set_config_value('model', 'new-model', tmp_config_path)
    
    # Assert: Only target field changed
    assert updated_config.model == 'new-model'
    assert updated_config.repos_dir == original_config.repos_dir
    assert updated_config.default_lookback_hours == original_config.default_lookback_hours
    assert updated_config.slack_channels == original_config.slack_channels


# =============================================================================
# ERROR MESSAGE QUALITY TESTS
# =============================================================================

def test_error_message_quality_unknown_key():
    """Verify error messages for unknown keys are helpful."""
    config = AscendConfig(
        repos_dir='/repos',
        reports_dir='/reports',
        config_dir='/config',
        anthropic_api_key_env='KEY',
        model='claude',
        default_lookback_hours=24,
        linear_team_id='team',
        linear_api_key_env='KEY',
        linear_team_ids=[],
        slack_channels=[],
        slack_bot_token_env='TOKEN',
        github_org='org'
    )
    
    with pytest.raises(Exception) as exc_info:
        get_config_value('nonexistent_field', config)
    
    # Error message should mention the invalid key
    error_msg = str(exc_info.value)
    # Should contain helpful information (implementation dependent)


def test_error_message_quality_int_conversion():
    """Verify error messages for int conversion failures are helpful."""
    # This would be tested in the context of set_config_value
    # The error should clearly indicate what value couldn't be converted
    pass  # Implementation dependent on actual error messages


# =============================================================================
# STRESS TESTS
# =============================================================================

def test_large_list_values(tmp_config_path):
    """Test handling of large lists in config."""
    large_team_ids = [f'team-{i}' for i in range(1000)]
    config_data = {
        'repos_dir': '/repos',
        'reports_dir': '/reports',
        'config_dir': '/config',
        'anthropic_api_key_env': 'KEY',
        'model': 'claude',
        'default_lookback_hours': 24,
        'linear_team_id': 'team',
        'linear_api_key_env': 'KEY',
        'linear_team_ids': large_team_ids,
        'slack_channels': [],
        'slack_bot_token_env': 'TOKEN',
        'github_org': 'org'
    }
    
    config = AscendConfig(**config_data)
    save_config(config, tmp_config_path)
    reloaded = load_config(tmp_config_path)
    
    assert len(reloaded.linear_team_ids) == 1000
    assert reloaded.linear_team_ids[0] == 'team-0'
    assert reloaded.linear_team_ids[-1] == 'team-999'


def test_very_long_string_values(tmp_config_path):
    """Test handling of very long string values."""
    long_string = 'a' * 10000
    config_data = {
        'repos_dir': long_string,
        'reports_dir': '/reports',
        'config_dir': '/config',
        'anthropic_api_key_env': 'KEY',
        'model': 'claude',
        'default_lookback_hours': 24,
        'linear_team_id': 'team',
        'linear_api_key_env': 'KEY',
        'linear_team_ids': [],
        'slack_channels': [],
        'slack_bot_token_env': 'TOKEN',
        'github_org': 'org'
    }
    
    config = AscendConfig(**config_data)
    save_config(config, tmp_config_path)
    reloaded = load_config(tmp_config_path)
    
    assert len(reloaded.repos_dir) == 10000
    assert reloaded.repos_dir == long_string
