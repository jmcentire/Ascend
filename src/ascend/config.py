"""Configuration system for Ascend.

Two-tier config: defaults + user overrides in ~/.ascend/config.yaml.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel


ASCEND_HOME = Path.home() / ".ascend"
CONFIG_PATH = ASCEND_HOME / "config.yaml"
DB_PATH = ASCEND_HOME / "ascend.db"
HISTORY_DIR = ASCEND_HOME / "history"
TRANSCRIPTS_DIR = ASCEND_HOME / "transcripts"
SCHEDULES_DIR = ASCEND_HOME / "schedules"

_DEFAULTS = {
    "repos_dir": str(Path.home() / "ascend-data" / "repos"),
    "reports_dir": str(Path.home() / "ascend-data" / "reports"),
    "config_dir": str(Path.home() / "ascend-data" / "config"),
    "anthropic_api_key_env": "ASCEND_ANTHROPIC_API_KEY",
    "model": "claude-sonnet-4-20250514",
    "default_lookback_hours": 24,
    "linear_team_id": "",
    "slack_channels": [],
    "github_org": "",
}


class AscendConfig(BaseModel):
    repos_dir: str = _DEFAULTS["repos_dir"]
    reports_dir: str = _DEFAULTS["reports_dir"]
    config_dir: str = _DEFAULTS["config_dir"]
    anthropic_api_key_env: str = "ASCEND_ANTHROPIC_API_KEY"
    model: str = _DEFAULTS["model"]
    default_lookback_hours: int = _DEFAULTS["default_lookback_hours"]
    linear_team_id: str = _DEFAULTS["linear_team_id"]
    linear_api_key_env: str = "LINEAR_API_KEY"
    linear_team_ids: list[str] = []
    slack_channels: list[str] = []
    slack_bot_token_env: str = "SLACK_BOT_TOKEN"
    github_org: str = ""
    manager_name: Optional[str] = None


def load_config(config_path: Optional[Path] = None) -> AscendConfig:
    """Load config from YAML, falling back to defaults."""
    path = config_path or CONFIG_PATH
    if path.exists():
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        return AscendConfig(**{k: v for k, v in raw.items() if v is not None})
    return AscendConfig()


def save_config(cfg: AscendConfig, config_path: Optional[Path] = None) -> None:
    """Save config to YAML."""
    path = config_path or CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(cfg.model_dump(), f, default_flow_style=False, sort_keys=False)


def get_config_value(key: str, cfg: Optional[AscendConfig] = None) -> str:
    """Get a single config value by key."""
    if cfg is None:
        cfg = load_config()
    data = cfg.model_dump()
    if key not in data:
        raise KeyError(f"Unknown config key: {key}")
    return str(data[key])


def set_config_value(key: str, value: str, config_path: Optional[Path] = None) -> AscendConfig:
    """Set a single config value and save."""
    cfg = load_config(config_path)
    data = cfg.model_dump()
    if key not in data:
        raise KeyError(f"Unknown config key: {key}")

    # Coerce types
    current = data[key]
    if isinstance(current, int):
        value = int(value)
    elif isinstance(current, list):
        value = [v.strip() for v in value.split(",")]
    data[key] = value

    cfg = AscendConfig(**data)
    save_config(cfg, config_path)
    return cfg
