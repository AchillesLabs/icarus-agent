"""Unit and integration tests for the Model Context Protocol (MCP) client subsystem."""

from __future__ import annotations

import sys

import pytest
from icarus_contracts.tools import ToolSafetyCategory
from icarus_core.mcp.adapter import McpToolAdapter, create_mcp_adapters, format_mcp_content
from icarus_core.mcp.client import McpClient
from icarus_core.mcp.protocol import (
    JsonRpcError,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
    McpToolSchema,
)
from icarus_core.mcp.transports import (
    MockTransport,
    SseTransport,
    StdioTransport,
)


def test_protocol_models():
    """Verify JSON-RPC 2.0 and MCP schema serialization."""
    req = JsonRpcRequest(id=1, method="initialize", params={"version": "1.0"})
    dumped = req.model_dump()
    assert dumped["jsonrpc"] == "2.0"
    assert dumped["id"] == 1
    assert dumped["method"] == "initialize"

    notif = JsonRpcNotification(method="notifications/initialized")
    assert notif.jsonrpc == "2.0"
    assert "id" not in notif.model_dump()

    res = JsonRpcResponse(id=1, result={"status": "ok"})
    assert res.result == {"status": "ok"}
    assert res.error is None

    err_res = JsonRpcResponse(
        id=2,
        error=JsonRpcError(code=-32600, message="Invalid Request"),
    )
    assert err_res.error.code == -32600

    schema = McpToolSchema(
        name="echo",
        description="Echo input text",
        inputSchema={"type": "object", "properties": {"msg": {"type": "string"}}},
    )
    assert schema.name == "echo"
    assert "msg" in schema.inputSchema["properties"]


@pytest.mark.asyncio
async def test_mcp_client_handshake_and_flow():
    """Test full MCP handshake, ping, list_tools, and call_tool with MockTransport."""
    transport = MockTransport()

    # Pre-queue initialize response
    transport.queue_response(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "test-mock-server", "version": "1.0.0"},
            },
        }
    )

    client = McpClient(transport=transport, server_name="mock_svc")
    assert not client.is_initialized

    init_res = await client.connect()
    assert client.is_initialized
    assert init_res.protocolVersion == "2024-11-05"
    assert client.server_info["name"] == "test-mock-server"

    # Verify incoming requests sent over transport
    init_msg = await transport.get_next_sent()
    assert init_msg["method"] == "initialize"
    notif_msg = await transport.get_next_sent()
    assert notif_msg["method"] == "notifications/initialized"

    # Ping
    transport.queue_response({"jsonrpc": "2.0", "id": 2, "result": {}})
    ping_ok = await client.ping()
    assert ping_ok is True
    ping_msg = await transport.get_next_sent()
    assert ping_msg["method"] == "ping"

    # List tools
    transport.queue_response(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "result": {
                "tools": [
                    {
                        "name": "lookup_weather",
                        "description": "Fetch current weather",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                            "required": ["city"],
                        },
                    }
                ]
            },
        }
    )
    tools = await client.list_tools()
    assert len(tools) == 1
    assert tools[0].name == "lookup_weather"
    assert tools[0].description == "Fetch current weather"

    # Call tool
    transport.queue_response(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "result": {"content": [{"type": "text", "text": "Tokyo: 22C, Clear sky"}]},
        }
    )
    call_res = await client.call_tool("lookup_weather", {"city": "Tokyo"})
    assert call_res["content"][0]["text"] == "Tokyo: 22C, Clear sky"

    await client.close()
    assert not client.is_initialized


@pytest.mark.asyncio
async def test_mcp_client_uninitialized_guard():
    """Verify client rejects tool operations if connect() was not called."""
    transport = MockTransport()
    client = McpClient(transport=transport, server_name="guard_svc")

    with pytest.raises(RuntimeError, match="MCP client is not initialized"):
        await client.list_tools()

    with pytest.raises(RuntimeError, match="MCP client is not initialized"):
        await client.call_tool("some_tool", {})


@pytest.mark.asyncio
async def test_mcp_client_init_error():
    """Verify client surfaces initialization failure from server."""
    transport = MockTransport()
    transport.queue_response(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32000, "message": "Server unauthorized"},
        }
    )
    client = McpClient(transport=transport, server_name="error_svc")
    with pytest.raises(RuntimeError, match="MCP server initialize error: Server unauthorized"):
        await client.connect()


def test_format_mcp_content():
    """Verify extraction and formatting of diverse MCP content types."""
    assert format_mcp_content(None) == ""
    assert format_mcp_content("raw string") == "raw string"

    data = {
        "content": [
            {"type": "text", "text": "Header info"},
            {"type": "image", "mimeType": "image/png"},
            {"type": "resource", "resource": {"uri": "file:///path/doc.txt"}},
        ]
    }
    formatted = format_mcp_content(data)
    assert "Header info" in formatted
    assert "[Image content: image/png]" in formatted
    assert "[Resource: file:///path/doc.txt]" in formatted


def test_mcp_tool_adapter_definition():
    """Verify tool naming, definition, and parameter exposure in McpToolAdapter."""
    transport = MockTransport()
    client = McpClient(transport=transport, server_name="browser")
    schema = McpToolSchema(
        name="navigate",
        description="Navigate to URL",
        inputSchema={
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    )

    adapter = McpToolAdapter(
        client=client,
        tool_schema=schema,
        safety_category=ToolSafetyCategory.REQUIRES_APPROVAL,
    )

    assert adapter.name == "mcp_browser_navigate"
    assert adapter.definition.name == "mcp_browser_navigate"
    assert adapter.definition.description == "Navigate to URL"
    assert adapter.definition.safety_category == ToolSafetyCategory.REQUIRES_APPROVAL
    assert "url" in adapter.definition.parameters["properties"]


def test_mcp_tool_adapter_execution_sync_and_async():
    """Test sync and async execution bridging and error handling."""
    transport = MockTransport()
    client = McpClient(transport=transport, server_name="default")
    client.is_initialized = True

    schema = McpToolSchema(
        name="fetch_status",
        description="Check status",
        inputSchema={"type": "object", "properties": {}},
    )
    adapter = McpToolAdapter(client=client, tool_schema=schema)

    # Success case
    transport.queue_response(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": "All systems operational"}],
                "isError": False,
            },
        }
    )
    result = adapter.execute(arguments={}, workspace_root=".", call_id="call-123")
    assert result.exit_code == 0
    assert "All systems operational" in result.output
    assert result.error is None
    assert result.call_id == "call-123"

    # MCP isError = True case
    transport.queue_response(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "content": [{"type": "text", "text": "Database connection timeout"}],
                "isError": True,
            },
        }
    )
    err_result = adapter.execute(arguments={}, workspace_root=".", call_id="call-456")
    assert err_result.exit_code == 1
    assert "Database connection timeout" in err_result.error

    # Exception / crash recovery
    transport.queue_response(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "error": {"code": -32603, "message": "Internal worker crashed"},
        }
    )
    crash_result = adapter.execute(arguments={}, workspace_root=".", call_id="call-789")
    assert crash_result.exit_code == 1
    assert "Internal worker crashed" in crash_result.error


@pytest.mark.asyncio
async def test_create_mcp_adapters_helper():
    """Verify dynamic discovery and bulk adapter creation helper."""
    transport = MockTransport()
    client = McpClient(transport=transport, server_name="analytics")
    client.is_initialized = True

    transport.queue_response(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": [
                    {"name": "query", "description": "Run query"},
                    {"name": "export", "description": "Export CSV"},
                ]
            },
        }
    )

    adapters = await create_mcp_adapters(client)
    assert len(adapters) == 2
    assert adapters[0].name == "mcp_analytics_query"
    assert adapters[1].name == "mcp_analytics_export"


@pytest.mark.asyncio
async def test_stdio_transport_real_subprocess():
    """Test StdioTransport with a mini Python JSON-RPC echo subprocess."""
    script = (
        "import sys, json\n"
        "while True:\n"
        "    line = sys.stdin.readline()\n"
        "    if not line:\n"
        "        break\n"
        "    req = json.loads(line.strip())\n"
        "    res = {'jsonrpc': '2.0', 'id': req.get('id'), 'result': {'echo': req.get('method')}}\n"
        "    sys.stdout.write(json.dumps(res) + '\\n')\n"
        "    sys.stdout.flush()\n"
    )

    transport = StdioTransport(
        command=sys.executable,
        args=["-c", script],
    )

    try:
        await transport.connect()
        assert transport.is_connected

        # Send test request
        await transport.send_message({"jsonrpc": "2.0", "id": 100, "method": "ping"})
        res = await transport.receive_message(timeout=5.0)
        assert res["id"] == 100
        assert res["result"]["echo"] == "ping"

    finally:
        await transport.close()
        assert not transport.is_connected


@pytest.mark.asyncio
async def test_sse_transport_mocked():
    """Verify SseTransport message flow and endpoint resolution."""
    transport = SseTransport(
        url="http://127.0.0.1:8000/sse",
        headers={"Authorization": "Bearer test-key"},
    )
    assert transport.url == "http://127.0.0.1:8000/sse"
    assert transport.post_url is None
    assert not transport.is_connected

    # Test error when sending before connected
    with pytest.raises(RuntimeError, match="SSE transport not connected"):
        await transport.send_message({"jsonrpc": "2.0", "id": 1})
