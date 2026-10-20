"""Unit tests for modular toolsets system and CLI management."""

from __future__ import annotations

from pathlib import Path

import pytest
from icarus_cli.toolsets_cmd import toolsets_app
from icarus_core.tools.registry import create_default_registry
from icarus_core.tools.toolsets import ToolsetManager
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def temp_toolsets_config(tmp_path: Path) -> Path:
    return tmp_path / "toolsets.json"


def test_toolset_manager_defaults(temp_toolsets_config: Path) -> None:
    mgr = ToolsetManager(config_path=temp_toolsets_config)
    toolsets = mgr.list_toolsets()
    assert len(toolsets) >= 7

    active = mgr.load_active_toolsets()
    assert "core" in active
    assert "filesystem" in active
    assert "web" in active
    assert "terminal" in active
    assert "integrations" in active
    assert "mcp" in active
    assert "automation" in active


def test_toolset_manager_enable_disable(temp_toolsets_config: Path) -> None:
    mgr = ToolsetManager(config_path=temp_toolsets_config)

    # Disable terminal
    assert mgr.disable_toolset("terminal") is True
    assert mgr.is_toolset_enabled("terminal") is False
    assert mgr.is_tool_enabled("run_command") is False
    assert mgr.is_tool_enabled("read_file") is True

    # Re-read from disk to ensure persistence
    mgr2 = ToolsetManager(config_path=temp_toolsets_config)
    assert mgr2.is_toolset_enabled("terminal") is False

    # Re-enable terminal
    assert mgr2.enable_toolset("terminal") is True
    assert mgr2.is_toolset_enabled("terminal") is True
    assert mgr2.is_tool_enabled("run_command") is True

    # Unknown toolset
    assert mgr2.enable_toolset("nonexistent_toolset") is False
    assert mgr2.disable_toolset("nonexistent_toolset") is False


def test_toolset_manager_reset(temp_toolsets_config: Path) -> None:
    mgr = ToolsetManager(config_path=temp_toolsets_config)
    mgr.disable_toolset("filesystem")
    mgr.disable_toolset("web")
    assert not mgr.is_toolset_enabled("filesystem")
    assert not mgr.is_toolset_enabled("web")

    mgr.reset_defaults()
    assert mgr.is_toolset_enabled("filesystem")
    assert mgr.is_toolset_enabled("web")


def test_toolset_filtering_in_registry() -> None:
    # Full registry without filtering
    full_reg = create_default_registry(load_mcp=False, apply_toolset_filter=False)
    assert full_reg.has("run_command")
    assert full_reg.has("read_file")
    assert full_reg.has("gmail_search")
    assert full_reg.has("drive_search")

    # Filtered registry disabling integrations
    filtered_reg = create_default_registry(
        load_mcp=False,
        apply_toolset_filter=True,
        active_toolsets={"core", "filesystem", "web", "terminal"},
    )
    assert filtered_reg.has("run_command")
    assert filtered_reg.has("read_file")
    assert not filtered_reg.has("gmail_search")
    assert not filtered_reg.has("calendar_events")
    assert not filtered_reg.has("drive_search")

    # Filtered registry disabling terminal
    no_term_reg = create_default_registry(
        load_mcp=False,
        apply_toolset_filter=True,
        active_toolsets={"core", "filesystem", "web", "integrations"},
    )
    assert not no_term_reg.has("run_command")
    assert no_term_reg.has("read_file")
    assert no_term_reg.has("drive_search")


def test_toolsets_cli_list() -> None:
    result = runner.invoke(toolsets_app, ["list"])
    assert result.exit_code == 0
    assert "Modular Toolsets" in result.output
    assert "filesystem" in result.output
    assert "integrations" in result.output


def test_toolsets_cli_enable_disable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("icarus_core.tools.toolsets.get_icarus_home", lambda: tmp_path)

    disable_res = runner.invoke(toolsets_app, ["disable", "terminal"])
    assert disable_res.exit_code == 0
    assert "DISABLED" in disable_res.output

    list_res = runner.invoke(toolsets_app, ["list"])
    assert list_res.exit_code == 0
    assert "Disabled" in list_res.output

    enable_res = runner.invoke(toolsets_app, ["enable", "terminal"])
    assert enable_res.exit_code == 0
    assert "ENABLED" in enable_res.output
