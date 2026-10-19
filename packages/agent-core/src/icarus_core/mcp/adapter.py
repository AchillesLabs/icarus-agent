"""Adapter converting remote MCP tools into standard Icarus BaseTool instances."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
from pathlib import Path
from typing import Any

from icarus_contracts.tools import ToolDefinition, ToolResult, ToolSafetyCategory

from icarus_core.mcp.client import McpClient
from icarus_core.mcp.protocol import McpToolSchema
from icarus_core.tools.base import BaseTool


def format_mcp_content(result: Any) -> str:
    """Extract and format textual output from an MCP tools/call result dictionary."""
    if not isinstance(result, dict):
        return str(result) if result is not None else ""

    content = result.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                item_type = item.get("type", "text")
                if item_type == "text":
                    parts.append(str(item.get("text", "")))
                elif item_type == "image":
                    mime = item.get("mimeType", "image/*")
                    parts.append(f"[Image content: {mime}]")
                elif item_type == "resource":
                    res = item.get("resource", {})
                    uri = res.get("uri", "unknown") if isinstance(res, dict) else str(res)
                    parts.append(f"[Resource: {uri}]")
                else:
                    parts.append(json.dumps(item))
            elif isinstance(item, str):
                parts.append(item)
            else:
                parts.append(str(item))
        return "\n".join(parts)

    if result:
        try:
            return json.dumps(result, indent=2)
        except Exception:
            return str(result)
    return ""


class McpToolAdapter(BaseTool):
    """Wraps an MCP tool schema and executes calls through an active McpClient."""

    def __init__(
        self,
        client: McpClient,
        tool_schema: McpToolSchema,
        tool_name: str | None = None,
        safety_category: ToolSafetyCategory = ToolSafetyCategory.SAFE_READ,
        timeout: float = 60.0,
    ) -> None:
        self.client = client
        self.tool_schema = tool_schema
        self.timeout = timeout
        self._safety_category = safety_category

        if tool_name:
            self._name = tool_name
        elif client.server_name and client.server_name != "default":
            self._name = f"mcp_{client.server_name}_{tool_schema.name}"
        else:
            self._name = (
                tool_schema.name
                if tool_schema.name.startswith("mcp_")
                else f"mcp_{tool_schema.name}"
            )

        parameters = tool_schema.inputSchema or {"type": "object", "properties": {}}
        description = tool_schema.description or f"MCP tool '{tool_schema.name}'"

        self._definition = ToolDefinition(
            name=self._name,
            description=description,
            parameters=parameters,
            safety_category=self._safety_category,
        )

    @property
    def definition(self) -> ToolDefinition:
        """Return tool metadata, parameter schema, and safety category."""
        return self._definition

    @property
    def name(self) -> str:
        """Helper returning the name of the tool."""
        return self._name

    async def execute_async(
        self,
        arguments: dict[str, Any],
        workspace_root: Path | str,
        call_id: str = "direct_call",
    ) -> ToolResult:
        """Asynchronously dispatch execution to the remote MCP server."""
        del workspace_root  # MCP tools handle their own remote context
        try:
            res = await self.client.call_tool(
                name=self.tool_schema.name,
                arguments=arguments,
                timeout=self.timeout,
            )
            output = format_mcp_content(res)
            is_error = bool(res.get("isError", False)) if isinstance(res, dict) else False

            if is_error:
                return ToolResult(
                    call_id=call_id,
                    name=self.name,
                    output=output,
                    error=output or "MCP tool execution returned an error.",
                    exit_code=1,
                )

            return ToolResult(
                call_id=call_id,
                name=self.name,
                output=output,
                exit_code=0,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                name=self.name,
                output="",
                error=f"MCP tool execution failed: {exc}",
                exit_code=1,
            )

    def execute(
        self,
        arguments: dict[str, Any],
        workspace_root: Path | str,
        call_id: str = "direct_call",
    ) -> ToolResult:
        """Synchronously execute the MCP tool, bridging running asyncio loops cleanly."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(
                    lambda: asyncio.run(self.execute_async(arguments, workspace_root, call_id))
                ).result()
        else:
            return asyncio.run(self.execute_async(arguments, workspace_root, call_id))


async def create_mcp_adapters(
    client: McpClient,
    timeout: float = 15.0,
) -> list[McpToolAdapter]:
    """Discover tools from an MCP client and instantiate McpToolAdapter wrappers."""
    schemas = await client.list_tools(timeout=timeout)
    return [McpToolAdapter(client=client, tool_schema=s) for s in schemas]
