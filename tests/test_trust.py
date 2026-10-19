"""Tests for workspace security verification and trusted directories management."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from icarus_cli.trust import (
    add_trusted_workspace,
    is_workspace_trusted,
    load_trusted_workspaces,
    verify_workspace_trust,
)


def test_trust_lifecycle(tmp_path: Path):
    """Verify adding, checking, and persisting trusted workspaces."""
    trust_file = tmp_path / "trusted_workspaces.json"

    with patch("icarus_cli.trust.get_trusted_workspaces_file", return_value=trust_file):
        # 1. Initially empty
        assert load_trusted_workspaces() == set()
        test_dir = tmp_path / "my_project"
        test_dir.mkdir()
        assert not is_workspace_trusted(test_dir)

        # 2. Add to trust
        add_trusted_workspace(test_dir)
        assert is_workspace_trusted(test_dir)
        assert str(test_dir.resolve()) in load_trusted_workspaces()

        # 3. File was created and contains valid JSON
        assert trust_file.exists()


def test_verify_workspace_trust_auto_approve(tmp_path: Path):
    """auto_approve=True bypasses interactive confirmation."""
    assert verify_workspace_trust(workspace_path=tmp_path, auto_approve=True) is True


def test_verify_workspace_trust_env_override(monkeypatch, tmp_path: Path):
    """ICARUS_TRUST_ALL=1 bypasses interactive confirmation."""
    monkeypatch.setenv("ICARUS_TRUST_ALL", "1")
    assert verify_workspace_trust(workspace_path=tmp_path) is True


def test_verify_workspace_trust_interactive_accept(tmp_path: Path):
    """Selecting yes marks workspace as trusted and returns True."""
    trust_file = tmp_path / "trusted_workspaces.json"
    project_dir = tmp_path / "project_a"
    project_dir.mkdir()

    with (
        patch("icarus_cli.trust.get_trusted_workspaces_file", return_value=trust_file),
        patch("sys.stdin.isatty", return_value=True),
        patch("questionary.select") as mock_select,
    ):
        mock_question = MagicMock()
        mock_question.ask.return_value = "1. Yes, I trust this folder"
        mock_select.return_value = mock_question

        result = verify_workspace_trust(workspace_path=project_dir)
        assert result is True
        assert is_workspace_trusted(project_dir)


def test_verify_workspace_trust_interactive_decline(tmp_path: Path):
    """Selecting no rejects workspace and returns False."""
    trust_file = tmp_path / "trusted_workspaces.json"
    project_dir = tmp_path / "project_b"
    project_dir.mkdir()

    with (
        patch("icarus_cli.trust.get_trusted_workspaces_file", return_value=trust_file),
        patch("sys.stdin.isatty", return_value=True),
        patch("questionary.select") as mock_select,
    ):
        mock_question = MagicMock()
        mock_question.ask.return_value = "2. No, exit"
        mock_select.return_value = mock_question

        result = verify_workspace_trust(workspace_path=project_dir)
        assert result is False
        assert not is_workspace_trusted(project_dir)
