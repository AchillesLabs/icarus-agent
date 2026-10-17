"""Tests for read-only filesystem tools: read_file and list_dir."""

import json
from pathlib import Path

from icarus_core.tools.filesystem import ListDirTool, ReadFileTool


def test_read_file_success_with_slicing(tmp_path: Path):
    """ReadFileTool reads lines and respects offset and limit."""
    test_file = tmp_path / "sample.py"
    test_file.write_text("line 1\nline 2\nline 3\nline 4\nline 5\n", encoding="utf-8")

    tool = ReadFileTool()
    result = tool.execute({"path": "sample.py", "offset": 2, "limit": 2}, workspace_root=tmp_path)

    assert result.exit_code == 0
    assert result.error is None
    assert "2: line 2" in result.output
    assert "3: line 3" in result.output
    assert "line 1" not in result.output
    assert "line 4" not in result.output


def test_read_file_not_found(tmp_path: Path):
    """ReadFileTool returns error when target file does not exist."""
    tool = ReadFileTool()
    result = tool.execute({"path": "non_existent.txt"}, workspace_root=tmp_path)

    assert result.exit_code == 1
    assert "not found" in result.error.lower()


def test_read_file_on_directory_errors(tmp_path: Path):
    """ReadFileTool returns error when path is a directory."""
    sub = tmp_path / "subdir"
    sub.mkdir()

    tool = ReadFileTool()
    result = tool.execute({"path": "subdir"}, workspace_root=tmp_path)

    assert result.exit_code == 1
    assert "directory" in result.error.lower()


def test_read_file_workspace_traversal_denied(tmp_path: Path):
    """ReadFileTool catches WorkspaceJailError and returns structured error result."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    tool = ReadFileTool()
    result = tool.execute({"path": "../outside.txt"}, workspace_root=workspace)

    assert result.exit_code == 1
    assert "escapes workspace" in result.error.lower() or "traversal" in result.error.lower()


def test_list_dir_flat(tmp_path: Path):
    """ListDirTool lists directory entries with size and type metadata."""
    (tmp_path / "file1.txt").write_text("hello")
    (tmp_path / "file2.py").write_text("print('test')")
    (tmp_path / "sub").mkdir()

    tool = ListDirTool()
    result = tool.execute({"path": "."}, workspace_root=tmp_path)

    assert result.exit_code == 0
    assert result.error is None
    entries = json.loads(result.output)
    names = [e["name"] for e in entries]
    assert "file1.txt" in names
    assert "file2.py" in names
    assert "sub" in names
    sub_entry = next(e for e in entries if e["name"] == "sub")
    assert sub_entry["is_dir"] is True


def test_list_dir_ignores_noise(tmp_path: Path):
    """ListDirTool excludes .git, __pycache__, and .venv directories."""
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("git config")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("app code")

    tool = ListDirTool()
    result = tool.execute({"path": "."}, workspace_root=tmp_path)

    assert result.exit_code == 0
    entries = json.loads(result.output)
    names = [e["name"] for e in entries]
    assert ".git" not in names
    assert "src" in names


def test_list_dir_recursive(tmp_path: Path):
    """ListDirTool traverses subdirectories when recursive is True."""
    sub = tmp_path / "pkg" / "nested"
    sub.mkdir(parents=True)
    (sub / "mod.py").write_text("code")

    tool = ListDirTool()
    result = tool.execute({"path": ".", "recursive": True, "max_depth": 3}, workspace_root=tmp_path)

    assert result.exit_code == 0
    entries = json.loads(result.output)
    paths = [e["path"].replace("\\", "/") for e in entries]
    assert any("pkg/nested" in p for p in paths)
    assert any("pkg/nested/mod.py" in p for p in paths)


def test_list_dir_not_found(tmp_path: Path):
    """ListDirTool returns error for non-existent directory."""
    tool = ListDirTool()
    result = tool.execute({"path": "missing_folder"}, workspace_root=tmp_path)

    assert result.exit_code == 1
    assert "not found" in result.error.lower()
