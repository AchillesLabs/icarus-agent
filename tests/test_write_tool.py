"""Tests for write_file tool and filesystem modifications."""

from pathlib import Path

from icarus_contracts.tools import ToolSafetyCategory
from icarus_core.tools.filesystem import WriteFileTool


def test_write_file_tool_definition():
    """WriteFileTool must have correct metadata, parameters, and REQUIRES_APPROVAL category."""
    tool = WriteFileTool()
    definition = tool.definition

    assert definition.name == "write_file"
    assert "write" in definition.description.lower()
    assert definition.safety_category == ToolSafetyCategory.REQUIRES_APPROVAL

    props = definition.parameters.get("properties", {})
    assert "path" in props
    assert "content" in props
    assert definition.parameters.get("required") == ["path", "content"]


def test_write_file_creates_file_and_parent_directories(tmp_path: Path):
    """Writing a file creates parent directories and writes UTF-8 content."""
    tool = WriteFileTool()
    rel_path = "nested/deep/hello.txt"
    content = "Hello, Icarus!\nLine 2.\n"

    result = tool.execute(
        arguments={"path": rel_path, "content": content},
        workspace_root=tmp_path,
        call_id="call_write_1",
    )

    assert result.exit_code == 0
    assert result.error is None
    assert result.call_id == "call_write_1"
    assert result.name == "write_file"
    assert "nested/deep/hello.txt" in result.output

    target_file = tmp_path / "nested" / "deep" / "hello.txt"
    assert target_file.is_file()
    assert target_file.read_text(encoding="utf-8") == content


def test_write_file_overwrites_existing_file(tmp_path: Path):
    """Writing to an existing file replaces its content."""
    tool = WriteFileTool()
    file_path = tmp_path / "notes.txt"
    file_path.write_text("Old content", encoding="utf-8")

    result = tool.execute(
        arguments={"path": "notes.txt", "content": "Brand new content"},
        workspace_root=tmp_path,
    )

    assert result.exit_code == 0
    assert result.error is None
    assert file_path.read_text(encoding="utf-8") == "Brand new content"


def test_write_file_jail_escape_rejected(tmp_path: Path):
    """Attempting to write outside the workspace raises workspace jail error."""
    tool = WriteFileTool()
    result = tool.execute(
        arguments={"path": "../outside.txt", "content": "malicious"},
        workspace_root=tmp_path,
    )

    assert result.exit_code == 1
    assert "escapes workspace boundary" in result.error.lower()
    assert not (tmp_path.parent / "outside.txt").exists()


def test_write_file_cannot_overwrite_directory(tmp_path: Path):
    """Attempting to write to a path that is already a directory returns error."""
    tool = WriteFileTool()
    sub_dir = tmp_path / "somedir"
    sub_dir.mkdir()

    result = tool.execute(
        arguments={"path": "somedir", "content": "content"},
        workspace_root=tmp_path,
    )

    assert result.exit_code == 1
    assert "is a directory" in result.error.lower()


def test_write_file_missing_arguments(tmp_path: Path):
    """Missing path or content returns clear error."""
    tool = WriteFileTool()

    res_no_path = tool.execute(arguments={"content": "abc"}, workspace_root=tmp_path)
    assert res_no_path.exit_code == 1
    assert "missing required argument 'path'" in res_no_path.error.lower()

    res_no_content = tool.execute(arguments={"path": "abc.txt"}, workspace_root=tmp_path)
    assert res_no_content.exit_code == 1
    assert "missing required argument 'content'" in res_no_content.error.lower()


def test_write_file_empty_content(tmp_path: Path):
    """Empty content is valid and creates an empty file."""
    tool = WriteFileTool()
    result = tool.execute(
        arguments={"path": "empty.txt", "content": ""},
        workspace_root=tmp_path,
    )

    assert result.exit_code == 0
    target_file = tmp_path / "empty.txt"
    assert target_file.is_file()
    assert target_file.read_text(encoding="utf-8") == ""
