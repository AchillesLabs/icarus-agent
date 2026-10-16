"""Tests for ConfigManager and config.toml serialization."""

from pathlib import Path

import pytest
from icarus_contracts import IcarusConfig
from icarus_core.config import ConfigManager


def test_config_manager_returns_defaults_when_file_missing(tmp_path: Path):
    cfg_file = tmp_path / "config.toml"
    manager = ConfigManager(config_path=cfg_file)
    config = manager.load_config()
    assert isinstance(config, IcarusConfig)
    assert config.default_provider == "grok"
    assert config.model == "grok-2"
    assert config.temperature == 0.7
    assert config.max_turns == 25


def test_config_manager_save_and_load(tmp_path: Path):
    cfg_file = tmp_path / "config.toml"
    manager = ConfigManager(config_path=cfg_file)

    custom_config = IcarusConfig(
        default_provider="openrouter",
        model="anthropic/claude-3.5-sonnet",
        temperature=0.2,
        max_turns=50,
        max_tokens_budget=200000,
    )
    manager.save_config(custom_config)

    assert cfg_file.exists()
    content = cfg_file.read_text(encoding="utf-8")
    assert "openrouter" in content
    assert "claude-3.5-sonnet" in content

    # Load back
    loaded = manager.load_config()
    assert loaded.default_provider == "openrouter"
    assert loaded.model == "anthropic/claude-3.5-sonnet"
    assert loaded.temperature == 0.2
    assert loaded.max_turns == 50
    assert loaded.max_tokens_budget == 200000


def test_config_manager_get_and_set(tmp_path: Path):
    cfg_file = tmp_path / "config.toml"
    manager = ConfigManager(config_path=cfg_file)

    assert manager.get("default_provider") == "grok"

    # Set with type conversion
    manager.set("temperature", "0.9")
    assert manager.get("temperature") == 0.9

    manager.set("max_turns", "40")
    assert manager.get("max_turns") == 40

    manager.set("model", "grok-beta")
    assert manager.get("model") == "grok-beta"


def test_config_manager_set_rejects_invalid_keys(tmp_path: Path):
    cfg_file = tmp_path / "config.toml"
    manager = ConfigManager(config_path=cfg_file)

    with pytest.raises(KeyError):
        manager.set("api_key", "secret-value")

    with pytest.raises(KeyError):
        manager.set("unknown_setting", "foo")


def test_config_manager_set_rejects_out_of_range_values(tmp_path: Path):
    cfg_file = tmp_path / "config.toml"
    manager = ConfigManager(config_path=cfg_file)

    with pytest.raises(ValueError):
        manager.set("temperature", "5.0")  # max is 2.0

    with pytest.raises(ValueError):
        manager.set("max_turns", "0")  # min is 1


def test_config_manager_list_settings(tmp_path: Path):
    cfg_file = tmp_path / "config.toml"
    manager = ConfigManager(config_path=cfg_file)
    settings = manager.list_settings()
    assert "default_provider" in settings
    assert "model" in settings
    assert "temperature" in settings
    assert "max_turns" in settings
    assert "max_tokens_budget" in settings
