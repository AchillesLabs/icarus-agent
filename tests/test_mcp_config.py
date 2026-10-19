"""Unit and integration tests for MCP configuration management and CLI commands."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from icarus_cli.main import app
from icarus_core.mcp.config import (
    McpConfigManager,
    McpServerConfig,
    load_configured_mcp_servers_sync,
)
from icarus_core.mcp.transports import SseTransport, StdioTransport
from icarus_core.tools.registry import ToolRegistry
from typer.testing import CliRunner


def test_mcp_server_config_validation():
    """Verify transport creation and validation rules."""
    stdio_cfg = McpServerConfig(
        transport="stdio",
        command="npx",
        args=["-y", "mcp-server"],
        env={"API_KEY": "secret"},
    )
    transport = stdio_cfg.create_transport()
    assert isinstance(transport, StdioTransport)
    assert transport.command == "npx"
    assert transport.args == ["-y", "mcp-server"]

    sse_cfg = McpServerConfig(
        transport="sse",
        url="https://example.com/sse",
        headers={"Authorization": "Bearer token"},
    )
    sse_transport = sse_cfg.create_transport()
    assert isinstance(sse_transport, SseTransport)
    assert sse_transport.url == "https://example.com/sse"

    # Missing command for stdio
    bad_stdio = McpServerConfig(transport="stdio", command=None)
    with pytest.raises(ValueError, match="Stdio transport requires a valid 'command'"):
        bad_stdio.create_transport()

    # Missing url for sse
    bad_sse = McpServerConfig(transport="sse", url=None)
    with pytest.raises(ValueError, match="SSE transport requires a valid 'url'"):
        bad_sse.create_transport()

    # Invalid transport
    bad_type = McpServerConfig(transport="ftp", command="ftp")
    with pytest.raises(ValueError, match="Unsupported MCP transport"):
        bad_type.create_transport()


def test_mcp_config_manager_crud(tmp_path: Path):
    """Test full CRUD lifecycle of McpConfigManager."""
    cfg_file = tmp_path / "mcp.json"
    mgr = McpConfigManager(config_path=cfg_file)

    # Empty file
    assert mgr.get_servers() == {}
    assert mgr.get_server("any") is None

    # Add stdio server
    srv1 = McpServerConfig(transport="stdio", command="node", args=["server.js"])
    mgr.add_server("node_srv", srv1)

    assert cfg_file.exists()
    loaded = mgr.get_servers()
    assert "node_srv" in loaded
    assert loaded["node_srv"].command == "node"

    # Add SSE server
    srv2 = McpServerConfig(transport="sse", url="https://mcp.ai/sse")
    mgr.add_server("remote_ai", srv2)

    servers = mgr.get_servers()
    assert len(servers) == 2
    assert mgr.get_server("remote_ai").url == "https://mcp.ai/sse"

    # Remove server
    removed = mgr.remove_server("node_srv")
    assert removed is True
    assert "node_srv" not in mgr.get_servers()

    # Remove non-existent
    removed_non_existent = mgr.remove_server("non_existent")
    assert removed_non_existent is False


def test_mcp_config_manager_flat_format_compatibility(tmp_path: Path):
    """Verify loading legacy or flat JSON format dictionary."""
    cfg_file = tmp_path / "flat_mcp.json"
    data = {
        "custom": {
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "custom_mcp"],
        }
    }
    cfg_file.write_text(json.dumps(data), encoding="utf-8")

    mgr = McpConfigManager(config_path=cfg_file)
    servers = mgr.get_servers()
    assert "custom" in servers
    assert servers["custom"].command == "python"


@pytest.mark.asyncio
async def test_mcp_config_test_server(tmp_path: Path):
    """Test test_server live handshake with a python stdio server."""
    server_script = (
        "import sys, json\n"
        "while True:\n"
        "    line = sys.stdin.readline()\n"
        "    if not line:\n"
        "        break\n"
        "    req = json.loads(line.strip())\n"
        "    req_id = req.get('id')\n"
        "    if req_id is None:\n"
        "        continue\n"
        "    method = req.get('method')\n"
        "    if method == 'initialize':\n"
        "        res = {'jsonrpc': '2.0', 'id': req_id, 'result': {'protocolVersion': '2024-11-05', 'capabilities': {}, 'serverInfo': {'name': 'test-daemon', 'version': '0.9'}}}\n"
        "    elif method == 'tools/list':\n"
        "        res = {'jsonrpc': '2.0', 'id': req_id, 'result': {'tools': [{'name': 'calc', 'description': 'Calculate math', 'inputSchema': {'type': 'object', 'properties': {'expr': {'type': 'string'}}}}]}}\n"
        "    else:\n"
        "        res = {'jsonrpc': '2.0', 'id': req_id, 'result': {}}\n"
        "    sys.stdout.write(json.dumps(res) + '\\n')\n"
        "    sys.stdout.flush()\n"
    )

    cfg_file = tmp_path / "mcp.json"
    mgr = McpConfigManager(config_path=cfg_file)
    mgr.add_server(
        "calc_daemon",
        McpServerConfig(
            transport="stdio",
            command=sys.executable,
            args=["-c", server_script],
        ),
    )

    info, tools = await mgr.test_server("calc_daemon")
    assert info["name"] == "test-daemon"
    assert len(tools) == 1
    assert tools[0].name == "calc"
    assert tools[0].description == "Calculate math"

    # Sync version
    info_sync, tools_sync = mgr.test_server_sync("calc_daemon")
    assert info_sync["name"] == "test-daemon"
    assert len(tools_sync) == 1


def test_mcp_auto_loader(tmp_path: Path):
    """Verify load_configured_mcp_servers auto-loads tools into ToolRegistry."""
    server_script = (
        "import sys, json\n"
        "while True:\n"
        "    line = sys.stdin.readline()\n"
        "    if not line:\n"
        "        break\n"
        "    req = json.loads(line.strip())\n"
        "    req_id = req.get('id')\n"
        "    if req_id is None:\n"
        "        continue\n"
        "    method = req.get('method')\n"
        "    if method == 'initialize':\n"
        "        res = {'jsonrpc': '2.0', 'id': req_id, 'result': {'protocolVersion': '2024-11-05', 'capabilities': {}, 'serverInfo': {'name': 'auto-srv', 'version': '1.0'}}}\n"
        "    elif method == 'tools/list':\n"
        "        res = {'jsonrpc': '2.0', 'id': req_id, 'result': {'tools': [{'name': 'ping_tool', 'description': 'Ping', 'inputSchema': {}}]}}\n"
        "    else:\n"
        "        res = {'jsonrpc': '2.0', 'id': req_id, 'result': {}}\n"
        "    sys.stdout.write(json.dumps(res) + '\\n')\n"
        "    sys.stdout.flush()\n"
    )

    cfg_file = tmp_path / "mcp.json"
    mgr = McpConfigManager(config_path=cfg_file)
    mgr.add_server(
        "ping_svc",
        McpServerConfig(
            transport="stdio",
            command=sys.executable,
            args=["-c", server_script],
        ),
    )

    registry = ToolRegistry()
    loaded_adapters = load_configured_mcp_servers_sync(registry, config_path=cfg_file)
    try:
        assert len(loaded_adapters) == 1
        assert registry.has("mcp_ping_svc_ping_tool")

        # Fault tolerance: broken server does not raise
        mgr.add_server(
            "broken_svc",
            McpServerConfig(
                transport="stdio",
                command="non_existent_binary_xyz_123",
                args=[],
            ),
        )
        reg2 = ToolRegistry()
        loaded2 = load_configured_mcp_servers_sync(reg2, config_path=cfg_file)
        assert len(loaded2) == 1
    finally:
        for a in loaded_adapters:
            import asyncio

            asyncio.run(a.client.close())


def test_cli_mcp_commands(tmp_path: Path):
    """Test CLI commands: add, list, test, and remove."""
    cfg_file = tmp_path / "mcp.json"
    runner = CliRunner()

    with patch(
        "icarus_cli.mcp_cmd.McpConfigManager",
        lambda *a, **kw: McpConfigManager(config_path=cfg_file),
    ):
        # 1. list when empty
        res = runner.invoke(app, ["mcp", "list"])
        assert res.exit_code == 0
        assert "No MCP servers configured" in res.stdout

        # 2. add stdio server
        res_add = runner.invoke(app, ["mcp", "add", "my_calc", "python", "-c", "print(1)"])
        assert res_add.exit_code == 0
        assert "Successfully registered MCP server 'my_calc'" in res_add.stdout

        # 3. add sse server
        res_sse = runner.invoke(
            app,
            ["mcp", "add", "my_remote", "https://mcp.example.com/sse", "--sse", "-H", "Auth=test"],
        )
        assert res_sse.exit_code == 0
        assert "Successfully registered MCP server 'my_remote'" in res_sse.stdout

        # 4. list with registered servers
        res_list = runner.invoke(app, ["mcp", "list"])
        assert res_list.exit_code == 0
        assert "my_calc" in res_list.stdout
        assert "my_remote" in res_list.stdout

        # 5. remove server
        res_rm = runner.invoke(app, ["mcp", "remove", "my_remote"])
        assert res_rm.exit_code == 0
        assert "Successfully removed MCP server 'my_remote'" in res_rm.stdout

        # 6. remove non-existent
        res_rm_bad = runner.invoke(app, ["mcp", "remove", "unknown_srv"])
        assert res_rm_bad.exit_code == 1

        # 7. test non-existent
        res_test_bad = runner.invoke(app, ["mcp", "test", "unknown_srv"])
        assert res_test_bad.exit_code == 1
