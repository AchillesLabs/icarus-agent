"""Native agent tool for Slack messaging and channel notifications."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from icarus_contracts.tools import ToolDefinition, ToolResult, ToolSafetyCategory

from icarus_core.tools.auth import ToolAuthManager
from icarus_core.tools.base import BaseTool


class SlackSendMessageTool(BaseTool):
    """Tool allowing the agent to post messages to Slack channels with approval."""

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="slack_send_message",
            description="Send a message or notification to a Slack channel.",
            parameters={
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "Slack channel name or ID (e.g., '#general', 'C12345').",
                    },
                    "text": {
                        "type": "string",
                        "description": "Message text to post.",
                    },
                },
                "required": ["channel", "text"],
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
        token = ToolAuthManager.get_token("slack")
        if not token:
            token = ToolAuthManager.prompt_authorization("slack")
            if not token:
                return ToolResult(
                    call_id=call_id,
                    name=self.name,
                    output="",
                    error="Slack authorization required. Please authorize at https://api.slack.com/apps or run `/connect slack`.",
                    exit_code=1,
                )

        channel = str(arguments.get("channel", "")).strip()
        text = str(arguments.get("text", "")).strip()

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers=headers,
                    json={"channel": channel, "text": text},
                )
                if resp.status_code == 200 and resp.json().get("ok"):
                    return ToolResult(
                        call_id=call_id,
                        name=self.name,
                        output=f"Successfully sent Slack message to {channel}.",
                        exit_code=0,
                    )
                err_msg = resp.json().get("error", resp.text)
                return ToolResult(
                    call_id=call_id,
                    name=self.name,
                    output="",
                    error=f"Slack API error: {err_msg}",
                    exit_code=1,
                )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                name=self.name,
                output="",
                error=f"Slack request failed: {exc}",
                exit_code=1,
            )
