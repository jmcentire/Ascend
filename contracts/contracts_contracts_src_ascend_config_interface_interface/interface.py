# === Ascend Configuration Management Interface (contracts_contracts_src_ascend_config_interface_interface) v1 ===
#  Dependencies: pathlib, typing, yaml, pydantic
# Two-tier configuration system for Ascend that manages defaults and user overrides stored in ~/.ascend/config.yaml. Provides functions to load, save, and manipulate configuration values with type coercion support for int and list types. Filters None values from YAML before model construction.

# Module invariants:
#   - CONFIG_PATH is always ~/.ascend/config.yaml
#   - ASCEND_HOME is always ~/.ascend
#   - _DEFAULTS dictionary defines fallback values for all config fields
#   - Config files are always YAML format with default_flow_style=False
#   - None values from YAML are always filtered before model construction
#   - All config values are convertible to string representation
#   - Type coercion for set_config_value only handles int and list types explicitly

class AscendConfig:
    """Pydantic model representing the complete Ascend configuration with default values"""
    repos_dir: Optional[str] = None          # optional, Directory path for repositories
    reports_dir: Optional[str] = None        # optional, Directory path for reports
    config_dir: Optional[str] = None         # optional, Directory path for configuration files
    anthropic_api_key_env: Optional[str] = None # optional, Environment variable name for Anthropic API key
    model: Optional[str] = None              # optional, Model identifier for Claude
    default_lookback_hours: Optional[int] = None # optional, Default number of hours to look back
    linear_team_id: Optional[str] = None     # optional, Linear team identifier
    linear_api_key_env: Optional[str] = None # optional, Environment variable name for Linear API key
    linear_team_ids: Optional[list[str]] = None # optional, List of Linear team identifiers
    slack_channels: Optional[list[str]] = None # optional, List of Slack channel identifiers
    slack_bot_token_env: Optional[str] = None # optional, Environment variable name for Slack bot token
    github_org: Optional[str] = None         # optional, GitHub organization name
    manager_name: Optional[str] = None       # optional, Optional manager name

def load_config(
    config_path: Optional[Path] = None,
) -> AscendConfig:
    """
    Load configuration from YAML file, falling back to defaults if file does not exist. Filters out None values from YAML before constructing AscendConfig.

    Postconditions:
      - Returns AscendConfig instance with either loaded values or defaults
      - None values from YAML are filtered out before model construction

    Errors:
      - yaml_parse_error (yaml.YAMLError): YAML file is malformed or invalid
      - pydantic_validation_error (pydantic.ValidationError): Loaded YAML data fails Pydantic validation
      - file_permission_error (PermissionError): Insufficient permissions to read config file
      - io_error (IOError): File system I/O error during read

    Side effects: none
    Idempotent: yes
    """
    ...

def save_config(
    cfg: AscendConfig,
    config_path: Optional[Path] = None,
) -> None:
    """
    Save AscendConfig instance to YAML file. Creates parent directories if they don't exist.

    Preconditions:
      - cfg must be a valid AscendConfig instance

    Postconditions:
      - Config file exists at specified path
      - Parent directories are created if they don't exist
      - YAML file contains serialized config data without flow style, unsorted keys

    Errors:
      - file_permission_error (PermissionError): Insufficient permissions to write config file or create directories
      - io_error (IOError): File system I/O error during write
      - disk_full_error (OSError): Insufficient disk space

    Side effects: none
    Idempotent: yes
    """
    ...

def get_config_value(
    key: str,
    cfg: Optional[AscendConfig] = None,
) -> str:
    """
    Get a single configuration value by key. Loads config if not provided, converts value to string.

    Preconditions:
      - key must exist in AscendConfig fields

    Postconditions:
      - Returns string representation of config value
      - Converts all values to string, even non-string types

    Errors:
      - unknown_key_error (KeyError): key does not exist in AscendConfig fields
          message: Unknown config key: {key}
      - yaml_parse_error (yaml.YAMLError): Config file is malformed when loading (if cfg is None)
      - pydantic_validation_error (pydantic.ValidationError): Loaded config data fails validation (if cfg is None)

    Side effects: none
    Idempotent: yes
    """
    ...

def set_config_value(
    key: str,
    value: str,
    config_path: Optional[Path] = None,
) -> AscendConfig:
    """
    Set a single configuration value by key with automatic type coercion, then save to file. Coerces value to int if current value is int, or to list[str] (comma-separated) if current value is list.

    Preconditions:
      - key must exist in AscendConfig fields

    Postconditions:
      - Config value is updated with type coercion applied
      - Updated config is saved to file
      - Returns updated AscendConfig instance
      - Integer fields are coerced via int(value)
      - List fields are coerced via comma-split and strip whitespace

    Errors:
      - unknown_key_error (KeyError): key does not exist in AscendConfig fields
          message: Unknown config key: {key}
      - int_conversion_error (ValueError): value cannot be converted to int when current field is int type
      - pydantic_validation_error (pydantic.ValidationError): Updated config data fails Pydantic validation
      - yaml_parse_error (yaml.YAMLError): Existing config file is malformed
      - file_permission_error (PermissionError): Insufficient permissions to read or write config file
      - io_error (IOError): File system I/O error during read or write

    Side effects: none
    Idempotent: no
    """
    ...

# ── REQUIRED EXPORTS ──────────────────────────────────
# Your implementation module MUST export ALL of these names
# with EXACTLY these spellings. Tests import them by name.
# __all__ = ['AscendConfig', 'load_config', 'save_config', 'get_config_value', 'set_config_value']
