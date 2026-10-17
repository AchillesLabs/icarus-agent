"""Tests for ToolRegistry and tool dispatch."""

from pathlib import Path

from icarus_contracts.tools import ToolCall
from icarus_core.tools.filesystem import ReadFileTool
from icarus_core.tools.registry import ToolRegistry, create_default_registry


def test_registry_register_and_get():
    """Registering a tool allows retrieval and inspection."""
    registry = ToolRegistry()
    tool = ReadFileTool()
    registry.register(tool)

    assert registry.has("read_file")
    assert registry.get("read_file") == tool
    assert not registry.has("unknown_tool")
    assert registry.get("unknown_tool") is None


def test_registry_export_schemas():
    """export_schemas returns OpenAI function definitions for all registered tools."""
    registry = ToolRegistry()
    registry.register(ReadFileTool())

    schemas = registry.export_schemas()
    assert len(schemas) == 1
    assert schemas[0]["type"] == "function"
    assert schemas[0]["function"]["name"] == "read_file"


def test_registry_dispatch_execution(tmp_path: Path):
    """ToolRegistry.execute dispatches ToolCall to target tool and returns ToolResult."""
    (tmp_path / "hello.txt").write_text("Hello, world!")

    registry = ToolRegistry()
    registry.register(ReadFileTool())

    call = ToolCall(id="call_abc", name="read_file", arguments={"path": "hello.txt"})
    result = registry.execute(call, workspace_root=tmp_path)

    assert result.call_id == "call_abc"
    assert result.name == "read_file"
    assert result.exit_code == 0
    assert "Hello, world!" in result.output


def test_registry_execute_unregistered_tool(tmp_path: Path):
    """Executing an unregistered tool returns error ToolResult without raising exception."""
    registry = ToolRegistry()
    call = ToolCall(id="call_xyz", name="nonexistent_tool", arguments={})
    result = registry.execute(call, workspace_root=tmp_path)

    assert result.call_id == "call_xyz"
    assert result.exit_code == 1
    assert "not found" in result.error.lower()


def test_create_default_registry():
    """create_default_registry includes read_file, list_dir, search, and write_file."""
    registry = create_default_registry()
    assert registry.has("read_file")
    assert registry.has("list_dir")
    assert registry.has("search")
    assert registry.has("write_file")
    definitions = registry.list_tools()
    names = [d.name for d in definitions]
    assert "read_file" in names
    assert "list_dir" in names
    assert "search" in names
    assert "write_file" in names

    search_def = next(d for d in definitions if d.name == "search")
    assert search_def.safety_category.value == "safe_read"

    write_def = next(d for d in definitions if d.name == "write_file")
    assert write_def.safety_category.value == "requires_approval"


def test_registry_dispatch_search(tmp_path: Path):
    """ToolRegistry dispatches search ToolCall to SearchTool and returns results."""
    (tmp_path / "hello.py").write_text("def find_this_symbol(): pass\n")
    registry = create_default_registry()

    call = ToolCall(
        id="call_search_1",
        name="search",
        arguments={"query": "find_this_symbol"},
    )
    result = registry.execute(call, workspace_root=tmp_path)

    assert result.call_id == "call_search_1"
    assert result.name == "search"
    assert result.exit_code == 0
    assert "find_this_symbol" in result.output


def test_registry_dispatch_write_file(tmp_path: Path):
    """ToolRegistry dispatches write_file ToolCall to WriteFileTool and creates file."""
    registry = create_default_registry()
    call = ToolCall(
        id="call_write_1",
        name="write_file",
        arguments={"path": "created_by_registry.txt", "content": "Registry wrote this!"},
    )
    result = registry.execute(call, workspace_root=tmp_path)

    assert result.call_id == "call_write_1"
    assert result.name == "write_file"
    assert result.exit_code == 0
    assert "created_by_registry.txt" in result.output

    target = tmp_path / "created_by_registry.txt"
    assert target.is_file()
    assert target.read_text(encoding="utf-8") == "Registry wrote this!"
