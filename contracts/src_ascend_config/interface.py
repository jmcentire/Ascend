# === Ascend Configuration System (src_ascend_config) v1 ===
#  Dependencies: pathlib, typing, yaml, pydantic
# Two-tier configuration system for Ascend. Manages user configuration stored in ~/.ascend/config.yaml with fallback to hard-coded defaults. Provides functions to load, save, get, and set configuration values with type coercion.

# Module invariants:
#   - ASCEND_HOME is always ~/.ascend
#   - CONFIG_PATH is always ~/.ascend/config.yaml unless overridden by parameter
#   - DB_PATH is always ~/.ascend/ascend.db
#   - HISTORY_DIR is always ~/.ascend/history
#   - TRANSCRIPTS_DIR is always ~/.ascend/transcripts
#   - SCHEDULES_DIR is always ~/.ascend/schedules
#   - _DEFAULTS dict provides fallback values for all configurable fields
#   - AscendConfig always has valid default values for all fields
#   - Config values are never None after load_config (None values are filtered out from YAML)
#   - Type coercion in set_config_value: int fields parsed as int, list fields split by comma, others remain string

class AscendConfig:
    """Pydantic model representing the complete Ascend configuration with all settings including directories, API keys, and integration settings."""
    repos_dir: str = None                    # optional, Directory for repository storage
    reports_dir: str = None                  # optional, Directory for report output
    config_dir: str = None                   # optional, Directory for additional config files
    anthropic_api_key_env: str = None        # optional, Environment variable name for Anthropic API key
    model: str = None                        # optional, Claude model identifier to use
    default_lookback_hours: int = None       # optional, Default time window for analysis in hours
    linear_team_id: str = None               # optional, Linear team identifier
    linear_api_key_env: str = None           # optional, Environment variable name for Linear API key
    linear_team_ids: list[str] = None        # optional, List of Linear team identifiers
    slack_channels: list[str] = None         # optional, List of Slack channel names to monitor
    slack_bot_token_env: str = None          # optional, Environment variable name for Slack bot token
    github_org: str = None                   # optional, GitHub organization name
    manager_name: Optional[str] = None       # optional, Optional manager name for personalization

class Path:
    """pathlib.Path representing file system paths"""
    pass

def load_config(
    config_path: Optional[Path] = None,
) -> AscendConfig:
    """
    Load configuration from YAML file or return default config if file does not exist. Reads from config_path or defaults to ~/.ascend/config.yaml. Filters out None values from YAML data.

    Postconditions:
      - Returns a valid AscendConfig instance
      - If config file exists and is valid YAML, returns config with values from file merged with defaults
      - If config file does not exist, returns AscendConfig with all default values

    Errors:
      - yaml_parse_error (yaml.YAMLError): YAML file is malformed or cannot be parsed
      - pydantic_validation_error (pydantic.ValidationError): YAML data contains invalid values for AscendConfig fields
      - io_error (IOError): File exists but cannot be read due to permissions or IO error

    Side effects: Reads from filesystem at config_path or CONFIG_PATH
    Idempotent: yes
    """
    ...

def save_config(
    cfg: AscendConfig,
    config_path: Optional[Path] = None,
) -> None:
    """
    Save AscendConfig to YAML file. Creates parent directories if they don't exist. Writes config as YAML with non-flow style and preserves key order.

    Preconditions:
      - cfg must be a valid AscendConfig instance

    Postconditions:
      - Config file exists at config_path or CONFIG_PATH
      - Config file contains YAML representation of cfg
      - Parent directory of config file exists

    Errors:
      - io_error (IOError): Cannot write to file due to permissions or IO error
      - os_error (OSError): Cannot create parent directories

    Side effects: Creates parent directories if they don't exist, Writes to filesystem at config_path or CONFIG_PATH
    Idempotent: yes
    """
    ...

def get_config_value(
    key: str,
    cfg: Optional[AscendConfig] = None,
) -> str:
    """
    Get a single configuration value by key. If cfg is not provided, loads config from disk. Returns string representation of the value.

    Preconditions:
      - key must be a valid field name in AscendConfig

    Postconditions:
      - Returns string representation of the config value for the given key

    Errors:
      - key_error (KeyError): key is not a valid field in AscendConfig
          message: Unknown config key: {key}
      - yaml_parse_error (yaml.YAMLError): Config file exists but YAML is malformed (when cfg is None)
      - io_error (IOError): Cannot read config file (when cfg is None)

    Side effects: If cfg is None, reads config file from disk via load_config()
    Idempotent: yes
    """
    ...

def set_config_value(
    key: str,
    value: str,
    config_path: Optional[Path] = None,
) -> AscendConfig:
    """
    Set a single configuration value by key and save to disk. Loads existing config, applies type coercion (int for int fields, comma-separated list for list fields), updates the value, and saves. Returns updated config.

    Preconditions:
      - key must be a valid field name in AscendConfig
      - If field type is int, value must be convertible to int
      - If field type is list, value should be comma-separated strings

    Postconditions:
      - Config file contains updated value for key
      - Returns AscendConfig with updated value
      - Value is type-coerced: int for int fields, list for list fields, string otherwise

    Errors:
      - key_error (KeyError): key is not a valid field in AscendConfig
          message: Unknown config key: {key}
      - value_error (ValueError): value cannot be converted to required type (e.g., non-numeric string for int field)
      - pydantic_validation_error (pydantic.ValidationError): Updated data fails Pydantic validation when constructing new AscendConfig
      - yaml_parse_error (yaml.YAMLError): Existing config file has malformed YAML
      - io_error (IOError): Cannot read or write config file

    Side effects: Reads existing config from disk, Writes updated config to disk, Creates parent directories if they don't exist
    Idempotent: no
    """
    ...

# ── REQUIRED EXPORTS ──────────────────────────────────
# Your implementation module MUST export ALL of these names
# with EXACTLY these spellings. Tests import them by name.
# __all__ = ['AscendConfig', 'load_config', 'save_config', 'get_config_value', 'set_config_value']
