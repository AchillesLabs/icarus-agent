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
