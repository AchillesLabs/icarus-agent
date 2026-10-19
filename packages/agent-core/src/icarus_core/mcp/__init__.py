"""Model Context Protocol (MCP) subsystem for Icarus Agent."""

from __future__ import annotations

from icarus_core.mcp.adapter import McpToolAdapter, create_mcp_adapters, format_mcp_content
from icarus_core.mcp.client import McpClient
from icarus_core.mcp.config import (
    McpConfigFile,
    McpConfigManager,
    McpServerConfig,
    load_configured_mcp_servers,
    load_configured_mcp_servers_sync,
)
from icarus_core.mcp.protocol import (
    LATEST_PROTOCOL_VERSION,
    JsonRpcError,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
    McpInitializeResult,
    McpServerCapabilities,
    McpToolSchema,
)
from icarus_core.mcp.transports import (
    BaseTransport,
    MockTransport,
    SseTransport,
    StdioTransport,
)

__all__ = [
    "LATEST_PROTOCOL_VERSION",
    "BaseTransport",
    "JsonRpcError",
    "JsonRpcNotification",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "McpClient",
    "McpConfigFile",
    "McpConfigManager",
    "McpInitializeResult",
    "McpServerCapabilities",
    "McpServerConfig",
    "McpToolAdapter",
    "McpToolSchema",
    "MockTransport",
    "SseTransport",
    "StdioTransport",
    "create_mcp_adapters",
    "format_mcp_content",
    "load_configured_mcp_servers",
    "load_configured_mcp_servers_sync",
]

