"""Configuration management and storage for Model Context Protocol (MCP) servers."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from icarus_core.mcp.adapter import McpToolAdapter
from icarus_core.mcp.client import McpClient
from icarus_core.mcp.protocol import McpToolSchema
from icarus_core.mcp.transports import BaseTransport, SseTransport, StdioTransport
from icarus_core.paths import get_icarus_mcp_config_path

if TYPE_CHECKING:
    from icarus_core.tools.registry import ToolRegistry

logger = logging.getLogger("icarus.mcp")


class McpServerConfig(BaseModel):
    """Configuration definition for an individual MCP server."""

    transport: str = Field(default="stdio", description="Transport type: 'stdio' or 'sse'")
    command: str | None = Field(default=None, description="Command executable for stdio transport")
    args: list[str] = Field(default_factory=list, description="Command arguments")
    env: dict[str, str] = Field(default_factory=dict, description="Environment variables")
    url: str | None = Field(default=None, description="HTTP/SSE URL for sse transport")
    headers: dict[str, str] = Field(
        default_factory=dict, description="HTTP headers for sse transport"
    )
    cwd: str | None = Field(default=None, description="Working directory for stdio subprocess")
    timeout: float = Field(default=30.0, description="Default timeout in seconds")

    def create_transport(self) -> BaseTransport:
        """Instantiate transport instance based on server configuration."""
        trans_type = self.transport.lower().strip()
        if trans_type == "sse":
            if not self.url:
                raise ValueError("SSE transport requires a valid 'url'.")
            return SseTransport(url=self.url, headers=self.headers)
        elif trans_type == "stdio":
            if not self.command:
                raise ValueError("Stdio transport requires a valid 'command'.")
            return StdioTransport(
                command=self.command,
                args=self.args,
                env=self.env or None,
                cwd=self.cwd or None,
            )
        else:
            raise ValueError(
                f"Unsupported MCP transport: '{self.transport}' (must be 'stdio' or 'sse')."
            )

    def create_client(self, server_name: str) -> McpClient:
        """Instantiate an uninitialized McpClient with the configured transport."""
        return McpClient(transport=self.create_transport(), server_name=server_name)


class McpConfigFile(BaseModel):
    """File schema matching standard Claude Desktop / Icarus mcpServers config."""

    mcpServers: dict[str, McpServerConfig] = Field(default_factory=dict)


class McpConfigManager:
    """Manages persistent MCP server definitions in ~/.icarus/mcp.json."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = (
            Path(config_path).expanduser().resolve()
            if config_path is not None
            else get_icarus_mcp_config_path()
        )

    def load(self) -> dict[str, McpServerConfig]:
        """Read and parse configured MCP servers from disk."""
        if not self.config_path.exists():
            return {}

        try:
            raw_text = self.config_path.read_text(encoding="utf-8").strip()
            if not raw_text:
                return {}
            data = json.loads(raw_text)
            if not isinstance(data, dict):
                return {}

            servers_dict = data.get("mcpServers", data)
            result: dict[str, McpServerConfig] = {}
            for name, cfg_data in servers_dict.items():
                if isinstance(cfg_data, dict):
                    result[name] = McpServerConfig.model_validate(cfg_data)
            return result
        except Exception as exc:
            logger.warning("Error reading MCP config from %s: %s", self.config_path, exc)
            return {}

    def save(self, servers: dict[str, McpServerConfig]) -> None:
        """Write MCP servers dictionary to disk atomically."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        dump_data = {
            "mcpServers": {name: cfg.model_dump(exclude_none=True) for name, cfg in servers.items()}
        }
        temp_path = self.config_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(dump_data, indent=2), encoding="utf-8")
        temp_path.replace(self.config_path)

    def get_servers(self) -> dict[str, McpServerConfig]:
        """Return all configured servers."""
        return self.load()

    def get_server(self, name: str) -> McpServerConfig | None:
        """Retrieve configuration for a specific server."""
        return self.load().get(name)

    def add_server(self, name: str, config: McpServerConfig) -> None:
        """Add or update an MCP server configuration."""
        servers = self.load()
        servers[name] = config
        self.save(servers)

    def remove_server(self, name: str) -> bool:
        """Remove a configured MCP server. Returns True if removed, False if not found."""
        servers = self.load()
        if name in servers:
            del servers[name]
            self.save(servers)
            return True
        return False

    async def test_server(
        self,
        name: str,
        timeout: float = 15.0,
    ) -> tuple[dict[str, Any], list[McpToolSchema]]:
        """Connect to configured server, execute handshake, and list discovered tools."""
        server = self.get_server(name)
        if not server:
            raise KeyError(f"Server '{name}' is not configured.")

        client = server.create_client(server_name=name)
        try:
            init_res = await client.connect(timeout=timeout)
            tools = await client.list_tools(timeout=timeout)
            return init_res.serverInfo, tools
        finally:
            await client.close()

    def test_server_sync(
        self,
        name: str,
        timeout: float = 15.0,
    ) -> tuple[dict[str, Any], list[McpToolSchema]]:
        """Synchronously test server connection bridging active event loops."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(
                    lambda: asyncio.run(self.test_server(name=name, timeout=timeout))
                ).result()
        else:
            return asyncio.run(self.test_server(name=name, timeout=timeout))


async def load_configured_mcp_servers(
    registry: ToolRegistry,
    config_path: Path | None = None,
    timeout: float = 10.0,
) -> list[McpToolAdapter]:
    """Auto-load configured MCP servers into an agent ToolRegistry during startup."""
    mgr = McpConfigManager(config_path=config_path)
    servers = mgr.get_servers()
    registered: list[McpToolAdapter] = []

    for name, cfg in servers.items():
        try:
            client = cfg.create_client(server_name=name)
            await client.connect(timeout=timeout)
            tools = await client.list_tools(timeout=timeout)
            for tool_schema in tools:
                adapter = McpToolAdapter(client=client, tool_schema=tool_schema)
                registry.register(adapter)
                registered.append(adapter)
            logger.info("Loaded %d tools from MCP server '%s'", len(tools), name)
        except Exception as exc:
            logger.warning(
                "Could not connect to configured MCP server '%s' during startup: %s",
                name,
                exc,
            )

    return registered


def load_configured_mcp_servers_sync(
    registry: ToolRegistry,
    config_path: Path | None = None,
    timeout: float = 10.0,
) -> list[McpToolAdapter]:
    """Synchronous wrapper for auto-loading configured MCP servers."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(
                lambda: asyncio.run(
                    load_configured_mcp_servers(registry, config_path=config_path, timeout=timeout)
                )
            ).result()
    else:
        return asyncio.run(
            load_configured_mcp_servers(registry, config_path=config_path, timeout=timeout)
        )
