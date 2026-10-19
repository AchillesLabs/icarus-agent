"""Transport implementations for Model Context Protocol (MCP) communication."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx


class BaseTransport(ABC):
    """Abstract base transport for bidirectional MCP communication."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish transport connection or launch child process."""
        ...

    @abstractmethod
    async def send_message(self, message: dict[str, Any]) -> None:
        """Send a JSON-RPC message to the remote MCP server."""
        ...

    @abstractmethod
    async def receive_message(self, timeout: float = 30.0) -> dict[str, Any]:
        """Receive a JSON-RPC message from the remote MCP server."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close connection and clean up resources."""
        ...


class StdioTransport(BaseTransport):
    """MCP transport communicating with a child process via standard I/O (stdin/stdout)."""

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
    ) -> None:
        self.command = command
        self.args = args or []
        self.env = env
        self.cwd = cwd
        self.process: asyncio.subprocess.Process | None = None

    @property
    def is_connected(self) -> bool:
        """Check if subprocess is running."""
        return self.process is not None and self.process.returncode is None

    async def connect(self) -> None:
        """Spawn child process with piped standard streams."""
        if self.process is not None:
            return

        cmd_path = shutil.which(self.command) or self.command
        merged_env = os.environ.copy()
        if self.env:
            merged_env.update(self.env)

        # On Windows, if invoking a .cmd or .bat or npx, shell or exec resolution
        use_shell = sys.platform == "win32" and (
            self.command.endswith((".cmd", ".bat"))
            or cmd_path.endswith((".cmd", ".bat"))
            or self.command in ("npx", "npm", "uvx")
        )

        try:
            if use_shell:
                # Format full shell command string
                cmd_str = f'"{cmd_path}" ' + " ".join(
                    f'"{a}"' if " " in a else a for a in self.args
                )
                self.process = await asyncio.create_subprocess_shell(
                    cmd_str,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=merged_env,
                    cwd=str(self.cwd) if self.cwd else None,
                )
            else:
                self.process = await asyncio.create_subprocess_exec(
                    cmd_path,
                    *self.args,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=merged_env,
                    cwd=str(self.cwd) if self.cwd else None,
                )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to spawn MCP server command '{self.command}': {exc}"
            ) from exc

    async def send_message(self, message: dict[str, Any]) -> None:
        """Send newline-delimited JSON message to child process stdin."""
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("MCP process stdin is not open.")

        raw = json.dumps(message) + "\n"
        self.process.stdin.write(raw.encode("utf-8"))
        await self.process.stdin.drain()

    async def receive_message(self, timeout: float = 30.0) -> dict[str, Any]:
        """Read a line of JSON from child process stdout."""
        if self.process is None or self.process.stdout is None:
            raise RuntimeError("MCP process stdout is not open.")

        try:
            while True:
                line_bytes = await asyncio.wait_for(self.process.stdout.readline(), timeout=timeout)
                if not line_bytes:
                    returncode = self.process.returncode
                    raise RuntimeError(
                        f"MCP server process exited unexpectedly (code {returncode})."
                    )

                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                # Parse JSON-RPC line
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    # Ignore non-JSON diagnostic noise from child stderr/stdout
                    continue
        except TimeoutError:
            raise TimeoutError(f"MCP server response timed out after {timeout}s.") from None

    async def close(self) -> None:
        """Cleanly terminate child process and close pipes."""
        if self.process is None:
            return

        proc = self.process
        self.process = None

        with contextlib.suppress(Exception):
            if proc.stdin and not proc.stdin.is_closing():
                proc.stdin.close()

        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=3.0)
        except Exception:
            with contextlib.suppress(Exception):
                proc.kill()


class SseTransport(BaseTransport):
    """MCP transport communicating over HTTP Server-Sent Events (SSE)."""

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.url = url
        self.headers = headers or {}
        self._client = client
        self._owns_client = client is None
        self._post_url: str | None = None
        self._sse_response: httpx.Response | None = None
        self._lines_iter: Any = None

    @property
    def post_url(self) -> str | None:
        """The resolved POST endpoint for sending messages."""
        return self._post_url

    @property
    def is_connected(self) -> bool:
        """Check if SSE connection is active."""
        return self._sse_response is not None

    async def connect(self) -> None:
        """Connect to the SSE stream and retrieve the client POST endpoint."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))

        headers = {"Accept": "text/event-stream"}
        headers.update(self.headers)

        req = self._client.build_request("GET", self.url, headers=headers)
        self._sse_response = await self._client.send(req, stream=True)
        if self._sse_response.status_code >= 400:
            await self.close()
            raise RuntimeError(
                f"SSE handshake failed with HTTP status {self._sse_response.status_code}."
            )

        self._lines_iter = self._sse_response.aiter_lines()

        # Read initial endpoint event
        msg = await self.receive_message(timeout=15.0)
        # Check if the initial event conveyed endpoint URL
        if "_endpoint" in msg:
            endpoint_path = msg["_endpoint"]
            # Resolve relative or absolute URL
            self._post_url = str(httpx.URL(self.url).join(endpoint_path))
        else:
            # Fallback to base URL
            self._post_url = self.url

    async def send_message(self, message: dict[str, Any]) -> None:
        """Send JSON-RPC message via HTTP POST to the established endpoint."""
        if self._client is None or not self._post_url:
            raise RuntimeError("SSE transport not connected.")

        resp = await self._client.post(self._post_url, json=message, headers=self.headers)
        if resp.status_code >= 400:
            raise RuntimeError(f"POST to MCP endpoint failed with HTTP status {resp.status_code}.")

    async def receive_message(self, timeout: float = 30.0) -> dict[str, Any]:
        """Read and parse next SSE event message."""
        if self._lines_iter is None:
            raise RuntimeError("SSE transport not connected.")

        event_name = "message"
        data_lines: list[str] = []

        try:
            while True:
                line = await asyncio.wait_for(anext(self._lines_iter), timeout=timeout)
                line = line.strip()
                if not line:
                    if data_lines:
                        payload = "\n".join(data_lines)
                        if event_name == "endpoint":
                            return {"_endpoint": payload.strip()}
                        try:
                            return json.loads(payload)
                        except json.JSONDecodeError:
                            data_lines = []
                            event_name = "message"
                            continue
                    continue

                if line.startswith("event:"):
                    event_name = line.partition(":")[2].strip()
                elif line.startswith("data:"):
                    data_lines.append(line.partition(":")[2].strip())
        except TimeoutError:
            raise TimeoutError(f"SSE response timed out after {timeout}s.") from None
        except StopAsyncIteration:
            raise RuntimeError("SSE connection closed by remote server.") from None

    async def close(self) -> None:
        """Close SSE stream and HTTP client."""
        if self._sse_response:
            with contextlib.suppress(Exception):
                await self._sse_response.aclose()
            self._sse_response = None

        if self._owns_client and self._client:
            with contextlib.suppress(Exception):
                await self._client.aclose()
            self._client = None


class MockTransport(BaseTransport):
    """In-memory mock transport for testing MCP client and handshake protocols."""

    def __init__(self, handler: Any = None) -> None:
        self.handler = handler
        self.outgoing: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.sent: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.sent_messages: list[dict[str, Any]] = []
        self.is_connected = False

    def queue_response(self, response: dict[str, Any]) -> None:
        """Queue a response message to be returned by receive_message."""
        self.outgoing.put_nowait(response)

    async def get_next_sent(self, timeout: float = 5.0) -> dict[str, Any]:
        """Retrieve the next sent message by the client."""
        return await asyncio.wait_for(self.sent.get(), timeout=timeout)

    async def connect(self) -> None:
        self.is_connected = True

    async def send_message(self, message: dict[str, Any]) -> None:
        self.sent_messages.append(message)
        await self.sent.put(message)
        if self.handler:
            response = self.handler(message)
            if response is not None:
                await self.outgoing.put(response)

    async def receive_message(self, timeout: float = 5.0) -> dict[str, Any]:
        try:
            return await asyncio.wait_for(self.outgoing.get(), timeout=timeout)
        except TimeoutError:
            raise TimeoutError("Mock transport timed out.") from None

    async def close(self) -> None:
        self.is_connected = False
