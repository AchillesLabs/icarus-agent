"""Model Context Protocol (MCP) JSON-RPC 2.0 protocol specifications and schemas."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

LATEST_PROTOCOL_VERSION = "2024-11-05"


class JsonRpcRequest(BaseModel):
    """JSON-RPC 2.0 request message."""

    jsonrpc: str = "2.0"
    id: int | str
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class JsonRpcNotification(BaseModel):
    """JSON-RPC 2.0 notification message (no id, no expected response)."""

    jsonrpc: str = "2.0"
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class JsonRpcError(BaseModel):
    """JSON-RPC 2.0 error object."""

    code: int
    message: str
    data: Any | None = None


class JsonRpcResponse(BaseModel):
    """JSON-RPC 2.0 response message."""

    jsonrpc: str = "2.0"
    id: int | str | None = None
    result: Any | None = None
    error: JsonRpcError | None = None


class McpToolSchema(BaseModel):
    """Discovered tool schema exposed by an MCP server."""

    name: str
    description: str = ""
    inputSchema: dict[str, Any] = Field(default_factory=dict)


class McpServerCapabilities(BaseModel):
    """Capabilities declared by the MCP server."""

    tools: dict[str, Any] | None = None
    prompts: dict[str, Any] | None = None
    resources: dict[str, Any] | None = None
    logging: dict[str, Any] | None = None


class McpInitializeResult(BaseModel):
    """Result returned by initialize request."""

    protocolVersion: str
    capabilities: McpServerCapabilities = Field(default_factory=McpServerCapabilities)
    serverInfo: dict[str, Any] = Field(default_factory=dict)
