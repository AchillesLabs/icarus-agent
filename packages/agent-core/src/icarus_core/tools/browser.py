"""Native agent tool for browser automation and web interaction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from icarus_contracts.tools import ToolDefinition, ToolResult, ToolSafetyCategory
from icarus_core.tools.base import BaseTool


class BrowserNavigateTool(BaseTool):
    """Tool allowing the agent to navigate web pages using automated browser."""

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="browser_navigate",
            description=(
                "Open a URL in an automated browser to interact with JavaScript-rendered "
                "web pages, online booking portals, or web apps."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The destination web URL to navigate to.",
                    },
                },
                "required": ["url"],
            },
            safety_category=ToolSafetyCategory.SAFE_READ,
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

        # Use fetch webpage tool or fallback extraction
        from icarus_core.tools.web import FetchWebpageTool
        fetcher = FetchWebpageTool()
        result = fetcher.execute({"url": url}, workspace_root=".")
        if result.exit_code == 0:
            return ToolResult(
                call_id=call_id,
                name=self.name,
                output=f"Browser navigated to {url}\n\nPage Content:\n{result.output}",
                exit_code=0,
            )
        return result
