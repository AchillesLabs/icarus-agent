"""Tests for icarus models CLI command and interactive model selection."""

import re
from pathlib import Path
from unittest.mock import patch

from icarus_cli.main import app
from icarus_cli.models_view import (
    render_models_table,
    resolve_model_by_input,
)
from icarus_contracts import DiscoveredModel
from typer.testing import CliRunner

runner = CliRunner()


def test_models_cli_help():
    result = runner.invoke(app, ["models", "--help"])
    assert result.exit_code == 0
    clean_stdout = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", result.stdout)
    assert "--provider" in clean_stdout
    assert "--set" in clean_stdout
    assert "--number" in clean_stdout


def test_models_cli_list_non_interactive(tmp_path: Path):
    mock_models = [
        DiscoveredModel(
            id="mock-free-model",
            name="Mock Free Model",
            provider="mock",
            context_window=128000,
            is_free=True,
            tier="Free",
            pricing_info="Free",
        ),
        DiscoveredModel(
            id="mock-paid-model",
            name="Mock Paid Model",
            provider="mock",
            context_window=64000,
            is_free=False,
            tier="Paid / Standard",
            pricing_info="$1.00/1M",
        ),
    ]

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_cli.main.fetch_provider_models", return_value=mock_models),
    ):
        result = runner.invoke(app, ["models", "--provider", "mock", "--non-interactive"])
        assert result.exit_code == 0
        assert "Mock Models Catalog" in result.stdout
        assert "mock-free-model" in result.stdout
        assert "mock-paid-model" in result.stdout


def test_models_cli_select_by_number(tmp_path: Path):
    mock_models = [
        DiscoveredModel(
            id="mock-model-1",
            name="Mock 1",
            provider="mock",
            context_window=128000,
            is_free=True,
            tier="Free",
        ),
        DiscoveredModel(
            id="mock-model-2",
            name="Mock 2",
            provider="mock",
            context_window=64000,
            is_free=False,
            tier="Paid / Standard",
        ),
    ]

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_cli.main.fetch_provider_models", return_value=mock_models),
    ):
        result = runner.invoke(app, ["models", "--provider", "mock", "-n", "2"])
        assert result.exit_code == 0
        assert "Active model switched to 'mock-model-2'" in result.stdout


def test_models_cli_select_by_set_flag(tmp_path: Path):
    mock_models = [
        DiscoveredModel(
            id="mock-custom-model",
            name="Mock Custom",
            provider="mock",
            context_window=128000,
            is_free=True,
            tier="Free",
        ),
    ]

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_cli.main.fetch_provider_models", return_value=mock_models),
    ):
        result = runner.invoke(app, ["models", "--provider", "mock", "-s", "mock-custom-model"])
        assert result.exit_code == 0
        assert "Active model switched to 'mock-custom-model'" in result.stdout


def test_resolve_model_by_input_helpers():
    models = [
        DiscoveredModel(
            id="model-a",
            name="Model A",
            provider="mock",
            context_window=128000,
            is_free=True,
            tier="Free",
        ),
        DiscoveredModel(
            id="model-b",
            name="Model B",
            provider="mock",
            context_window=64000,
            is_free=False,
            tier="Paid / Standard",
        ),
    ]

    assert resolve_model_by_input(models, number=1) == "model-a"
    assert resolve_model_by_input(models, number=2) == "model-b"
    assert resolve_model_by_input(models, model_id="MODEL-B") == "model-b"


def test_render_models_table_empty():
    # Should not raise exception
    render_models_table([])
