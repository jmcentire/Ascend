"""Tests for configuration system."""

import pytest
import yaml

from ascend.config import AscendConfig, load_config, save_config, get_config_value, set_config_value


@pytest.fixture
def config_path(tmp_path):
    return tmp_path / "config.yaml"


def test_default_config():
    cfg = AscendConfig()
    assert cfg.model == "claude-sonnet-4-20250514"
    assert cfg.default_lookback_hours == 24
    assert cfg.github_org == ""


def test_save_and_load(config_path):
    cfg = AscendConfig(model="test-model", default_lookback_hours=48)
    save_config(cfg, config_path)
    assert config_path.exists()

    loaded = load_config(config_path)
    assert loaded.model == "test-model"
    assert loaded.default_lookback_hours == 48


def test_load_missing_returns_defaults(tmp_path):
    cfg = load_config(tmp_path / "nonexistent.yaml")
    assert cfg.model == "claude-sonnet-4-20250514"


def test_get_config_value():
    cfg = AscendConfig()
    assert get_config_value("model", cfg) == "claude-sonnet-4-20250514"


def test_get_config_value_unknown():
    cfg = AscendConfig()
    with pytest.raises(KeyError):
        get_config_value("nonexistent_key", cfg)


def test_set_config_value(config_path):
    save_config(AscendConfig(), config_path)
    cfg = set_config_value("model", "new-model", config_path)
    assert cfg.model == "new-model"

    # Verify persisted
    loaded = load_config(config_path)
    assert loaded.model == "new-model"


def test_set_config_int_coercion(config_path):
    save_config(AscendConfig(), config_path)
    cfg = set_config_value("default_lookback_hours", "72", config_path)
    assert cfg.default_lookback_hours == 72


def test_set_config_unknown_key(config_path):
    save_config(AscendConfig(), config_path)
    with pytest.raises(KeyError):
        set_config_value("fake_key", "value", config_path)


def test_config_yaml_format(config_path):
    cfg = AscendConfig(model="test")
    save_config(cfg, config_path)
    raw = yaml.safe_load(config_path.read_text())
    assert raw["model"] == "test"
    assert isinstance(raw["slack_channels"], list)
