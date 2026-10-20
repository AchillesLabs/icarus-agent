"""Native agent tool for executing general HTTP/REST requests and webhooks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from icarus_contracts.tools import ToolDefinition, ToolResult, ToolSafetyCategory
from icarus_core.tools.base import BaseTool


class HttpRequestTool(BaseTool):
    """Tool allowing the agent to send HTTP/REST API calls and webhooks."""

    def __init__(self, timeout: float = 30.0) -> None:
        self.default_timeout = timeout
        self._definition = ToolDefinition(
            name="http_request",
            description=(
                "Send an HTTP request (GET, POST, PUT, DELETE, PATCH) to an external "
                "REST API, webhook, payment gateway, or booking endpoint with custom headers, "
                "query parameters, and body."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The destination URL (must start with http:// or https://).",
                    },
                    "method": {
                        "type": "string",
                        "description": "HTTP method to use (default: 'GET').",
                        "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                    },
                    "headers": {
                        "type": "object",
                        "description": "Optional HTTP request headers dictionary.",
                    },
                    "params": {
                        "type": "object",
                        "description": "Optional URL query parameters dictionary.",
                    },
                    "json_body": {
                        "type": "object",
                        "description": "Optional JSON payload object for POST/PUT/PATCH requests.",
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Request timeout in seconds (default: 30.0).",
                    },
                },
                "required": ["url"],
            },
            safety_category=ToolSafetyCategory.REQUIRES_APPROVAL,
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def execute(
        self,
        arguments: dict[str, Any],
        workspace_root: Path | str,
        call_id: str = "direct_call",
    ) -> ToolResult:
        del workspace_root
        url = str(arguments.get("url", "")).strip()
        if not url:
            return ToolResult(
                call_id=call_id,
                name=self.name,
                output="",
                error="Required parameter 'url' is missing or empty.",
                exit_code=1,
            )

        if not (url.startswith("http://") or url.startswith("https://")):
            return ToolResult(
                call_id=call_id,
                name=self.name,
                output="",
                error="Invalid URL format. URL must begin with http:// or https://",
                exit_code=1,
            )

        method = str(arguments.get("method", "GET")).strip().upper()
        headers = arguments.get("headers") or {}
        params = arguments.get("params") or {}
        json_body = arguments.get("json_body")
        timeout = float(arguments.get("timeout", self.default_timeout))

        if not isinstance(headers, dict):
            headers = {}
        if not isinstance(params, dict):
            params = {}

        headers.setdefault("User-Agent", "IcarusAgent/0.1.0")

        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                response = client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_body if json_body is not None else None,
                )

                content_type = response.headers.get("content-type", "")
                text_body = response.text

                # Attempt to pretty-print JSON if applicable
                if "application/json" in content_type.lower():
                    try:
                        parsed = response.json()
                        text_body = json.dumps(parsed, indent=2)
                    except Exception:
                        pass

                if len(text_body) > 30000:
                    text_body = text_body[:30000] + f"\n... (truncated {len(text_body) - 30000} characters)"

                status_line = f"HTTP {response.status_code} {response.reason_phrase}"
                output = f"Status: {status_line}\nURL: {response.url}\n\nResponse Body:\n{text_body}"

                return ToolResult(
                    call_id=call_id,
                    name=self.name,
                    output=output,
                    exit_code=0 if response.is_success else 1,
                    error="" if response.is_success else f"HTTP error status: {response.status_code}",
                )
        except httpx.TimeoutException:
            return ToolResult(
                call_id=call_id,
                name=self.name,
                output="",
                error=f"HTTP request timed out after {timeout} seconds.",
                exit_code=1,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                name=self.name,
                output="",
                error=f"HTTP request execution failed: {exc}",
                exit_code=1,
            )
