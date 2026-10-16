"""CLI end-to-end integration tests using Typer CliRunner."""

from pathlib import Path
from unittest.mock import patch

from icarus_cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


def test_cli_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout
    assert "icarus" in result.stdout.lower()


def test_cli_help_flag():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "doctor" in result.stdout
    assert "Icarus" in result.stdout


def test_cli_doctor_healthy(tmp_path: Path):
    with patch("icarus_core.paths.get_icarus_home", return_value=tmp_path):
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "Doctor" in result.stdout
        assert "PASS" in result.stdout or "OK" in result.stdout
        assert "healthy" in result.stdout.lower()


def test_cli_doctor_unhealthy_returns_exit_code_1():
    with patch("sys.version_info", (3, 11, 0, "final", 0)), patch("sys.version", "3.11.0"):
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 1
        assert "FAIL" in result.stdout or "incompatible" in result.stdout.lower()


def test_cli_doctor_auto_migrates_database(tmp_path: Path):
    db_file = tmp_path / "icarus.db"
    assert not db_file.exists()

    with patch("icarus_core.paths.get_icarus_home", return_value=tmp_path):
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "Database & Migrations" in result.stdout
        assert "PASS" in result.stdout

    assert db_file.exists()
    from icarus_core.persistence.database import DatabaseManager
    from sqlalchemy import inspect

    manager = DatabaseManager(db_url=f"sqlite:///{db_file.as_posix()}")
    tables = inspect(manager.engine).get_table_names()
    assert "sessions" in tables
    assert "messages" in tables
    assert "agent_runs" in tables


def test_cli_config_list(tmp_path: Path):
    with patch("icarus_core.paths.get_icarus_home", return_value=tmp_path):
        result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0
        assert "default_provider" in result.stdout
        assert "grok" in result.stdout
        assert "temperature" in result.stdout


def test_cli_config_set_valid_and_invalid(tmp_path: Path):
    with patch("icarus_core.paths.get_icarus_home", return_value=tmp_path):
        # Valid set
        set_res = runner.invoke(app, ["config", "set", "temperature", "0.3"])
        assert set_res.exit_code == 0
        assert "0.3" in set_res.stdout

        # Verify list updated
        list_res = runner.invoke(app, ["config", "list"])
        assert "0.3" in list_res.stdout

        # Invalid key
        err_res = runner.invoke(app, ["config", "set", "unknown_key", "val"])
        assert err_res.exit_code != 0

        # Invalid range
        range_res = runner.invoke(app, ["config", "set", "temperature", "5.0"])
        assert range_res.exit_code != 0


def test_cli_init_non_interactive(tmp_path: Path):
    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("keyring.set_password") as mock_set_pw,
    ):
        result = runner.invoke(
            app,
            ["init", "--provider", "grok", "--api-key", "xai-test-key-12345", "--non-interactive"],
        )
        assert result.exit_code == 0
        assert "initialization complete" in result.stdout.lower()
        mock_set_pw.assert_called_once_with("icarus", "grok", "xai-test-key-12345")

        # Config file created
        config_path = tmp_path / "config.toml"
        assert config_path.exists()
        assert "grok" in config_path.read_text(encoding="utf-8")
        # Ensure secret is NOT in config.toml
        assert "xai-test-key-12345" not in config_path.read_text(encoding="utf-8")
        # DB file created
        assert (tmp_path / "icarus.db").exists()


def test_cli_init_interactive(tmp_path: Path):
    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("keyring.set_password") as mock_set_pw,
    ):
        # Simulate typing provider then api key
        result = runner.invoke(app, ["init"], input="grok\nxai-interactive-key\n")
        assert result.exit_code == 0
        mock_set_pw.assert_called_once_with("icarus", "grok", "xai-interactive-key")
