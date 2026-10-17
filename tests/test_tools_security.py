"""Tests for workspace boundary jailing and path resolution."""

from pathlib import Path

import pytest
from icarus_contracts.exceptions import WorkspaceJailError
from icarus_core.tools.security import resolve_workspace_path


def test_resolve_relative_path_within_workspace(tmp_path: Path):
    """Relative paths within workspace resolve correctly."""
    target_file = tmp_path / "src" / "main.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("print('ok')")

    resolved = resolve_workspace_path("src/main.py", workspace_root=tmp_path)
    assert resolved == target_file.resolve()


def test_resolve_root_or_dot(tmp_path: Path):
    """Dot or empty string resolves to workspace root."""
    resolved = resolve_workspace_path(".", workspace_root=tmp_path)
    assert resolved == tmp_path.resolve()

    resolved_empty = resolve_workspace_path("", workspace_root=tmp_path)
    assert resolved_empty == tmp_path.resolve()


def test_resolve_absolute_path_inside_workspace(tmp_path: Path):
    """Absolute path inside workspace is permitted."""
    inside = tmp_path / "docs" / "readme.md"
    inside.parent.mkdir(parents=True)
    inside.write_text("# Readme")

    resolved = resolve_workspace_path(inside, workspace_root=tmp_path)
    assert resolved == inside.resolve()


def test_reject_traversal_outside_workspace_with_relative_dots(tmp_path: Path):
    """Paths attempting to traverse outside workspace with '../' raise WorkspaceJailError."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(WorkspaceJailError) as exc_info:
        resolve_workspace_path("../outside.txt", workspace_root=workspace)

    err_str = str(exc_info.value).lower()
    assert "escapes workspace" in err_str or "traversal" in err_str


def test_reject_absolute_path_outside_workspace(tmp_path: Path):
    """Absolute paths outside workspace raise WorkspaceJailError."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "other" / "secret.env"

    with pytest.raises(WorkspaceJailError):
        resolve_workspace_path(outside, workspace_root=workspace)
