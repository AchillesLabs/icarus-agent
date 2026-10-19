"""Asynchronous Model Context Protocol (MCP) Client."""

from __future__ import annotations

from typing import Any

from icarus_core.mcp.protocol import (
    LATEST_PROTOCOL_VERSION,
    JsonRpcNotification,
    JsonRpcRequest,
    McpInitializeResult,
    McpServerCapabilities,
    McpToolSchema,
)
from icarus_core.mcp.transports import BaseTransport


class McpClient:
    """Asynchronous client managing MCP lifecycle, tool discovery, and invocations."""

    def __init__(
        self,
        transport: BaseTransport,
        server_name: str = "default",
    ) -> None:
        self.transport = transport
        self.server_name = server_name
        self._request_counter = 0
        self.is_initialized = False
        self.server_info: dict[str, Any] = {}
        self.server_capabilities = McpServerCapabilities()

    def _next_id(self) -> int:
        self._request_counter += 1
        return self._request_counter

    async def connect(self, timeout: float = 15.0) -> McpInitializeResult:
        """Establish transport connection and execute full MCP initialization handshake."""
        await self.transport.connect()

        # 1. Send initialize request
        req_id = self._next_id()
        init_req = JsonRpcRequest(
            id=req_id,
            method="initialize",
            params={
                "protocolVersion": LATEST_PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {},
                    "roots": {"listChanged": False},
                },
                "clientInfo": {
                    "name": "icarus-agent",
                    "version": "0.1.0",
                },
            },
        )
        await self.transport.send_message(init_req.model_dump())

        # 2. Receive initialize response
        res = await self.transport.receive_message(timeout=timeout)
        if res.get("error"):
            err = res["error"]
            raise RuntimeError(f"MCP server initialize error: {err.get('message', err)}")

        result_data = res.get("result", {})
        init_result = McpInitializeResult.model_validate(result_data)
        self.server_info = init_result.serverInfo
        self.server_capabilities = init_result.capabilities

        # 3. Send notifications/initialized notification
        notif = JsonRpcNotification(
            method="notifications/initialized",
            params={},
        )
        await self.transport.send_message(notif.model_dump())
        self.is_initialized = True
        return init_result

    async def ping(self, timeout: float = 5.0) -> bool:
        """Verify server responsiveness via JSON-RPC ping."""
        req_id = self._next_id()
        ping_req = JsonRpcRequest(id=req_id, method="ping")
        await self.transport.send_message(ping_req.model_dump())
        res = await self.transport.receive_message(timeout=timeout)
        return res.get("error") is None

    async def list_tools(self, timeout: float = 15.0) -> list[McpToolSchema]:
        """Query and return all tool definitions exposed by the MCP server."""
        if not self.is_initialized:
            raise RuntimeError("MCP client is not initialized. Call connect() first.")

        req_id = self._next_id()
        req = JsonRpcRequest(id=req_id, method="tools/list", params={})
        await self.transport.send_message(req.model_dump())

        res = await self.transport.receive_message(timeout=timeout)
        if res.get("error"):
            err = res["error"]
            raise RuntimeError(f"MCP tools/list failed: {err.get('message', err)}")

        tools_data = res.get("result", {}).get("tools", [])
        return [McpToolSchema.model_validate(t) for t in tools_data]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        """Execute a remote MCP tool and return its result payload."""
        if not self.is_initialized:
            raise RuntimeError("MCP client is not initialized. Call connect() first.")

        req_id = self._next_id()
        req = JsonRpcRequest(
            id=req_id,
            method="tools/call",
            params={
                "name": name,
                "arguments": arguments or {},
            },
        )
        await self.transport.send_message(req.model_dump())

        res = await self.transport.receive_message(timeout=timeout)
        if res.get("error"):
            err = res["error"]
            raise RuntimeError(f"MCP tool '{name}' call failed: {err.get('message', err)}")

        return res.get("result", {})

    async def close(self) -> None:
        """Close connection and clean up resources."""
        self.is_initialized = False
        await self.transport.close()
