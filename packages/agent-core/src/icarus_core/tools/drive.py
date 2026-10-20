"""Native agent tools for Google Drive file search and content retrieval."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from icarus_contracts.tools import ToolDefinition, ToolResult, ToolSafetyCategory
from icarus_core.integrations.clients.google_client import GoogleDriveApiClient
from icarus_core.tools.auth import ToolAuthManager
from icarus_core.tools.base import BaseTool


class DriveSearchTool(BaseTool):
    """Tool allowing the agent to search Google Drive files."""

    def __init__(self, client: GoogleDriveApiClient | None = None) -> None:
        self.client = client
        self._definition = ToolDefinition(
            name="drive_search",
            description="Search your Google Drive for files and documents by title or keyword.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "File name search query or keyword (e.g. 'budget', 'roadmap', 'invoice').",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of files to return (default: 5).",
                    },
                },
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
        token = ToolAuthManager.get_access_token("google") or ToolAuthManager.get_token("drive")
        if not token and self.client is None:
            return ToolResult(
                call_id=call_id,
                name=self.name,
                output="",
                error=(
                    "Google Drive authorization required. Please connect your Google account with "
                    "`icarus integrations connect google`."
                ),
                exit_code=1,
            )

        query = str(arguments.get("query", "")).strip()
        max_results = int(arguments.get("max_results", 5))

        try:
            api_client = self.client or GoogleDriveApiClient(access_token=token or "")
            files = api_client.search_files(query=query, max_results=max_results)
            if not files:
                return ToolResult(
                    call_id=call_id,
                    name=self.name,
                    output=f"No files found in Google Drive matching '{query}'.",
                    exit_code=0,
                )
            lines = [f"Google Drive Search Results ({len(files)} files):\n"]
            for f in files:
                lines.append(f"• {f.get('name', 'Untitled')} (ID: {f.get('id')}, Type: {f.get('mimeType')})")
            return ToolResult(call_id=call_id, name=self.name, output="\n".join(lines).strip(), exit_code=0)
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                name=self.name,
                output="",
                error=f"Google Drive search error: {exc}",
                exit_code=1,
            )


class DriveReadFileTool(BaseTool):
    """Tool allowing the agent to read file content from Google Drive."""

    def __init__(self, client: GoogleDriveApiClient | None = None) -> None:
        self.client = client
        self._definition = ToolDefinition(
            name="drive_read_file",
            description="Retrieve and read the text contents of a document or file stored in Google Drive.",
            parameters={
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "The unique Google Drive file ID to read.",
                    },
                    "max_bytes": {
                        "type": "integer",
                        "description": "Maximum character length to retrieve (default: 20000).",
                    },
                },
                "required": ["file_id"],
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
        token = ToolAuthManager.get_access_token("google") or ToolAuthManager.get_token("drive")
        if not token and self.client is None:
            return ToolResult(
                call_id=call_id,
                name=self.name,
                output="",
                error=(
                    "Google Drive authorization required. Please connect your Google account with "
                    "`icarus integrations connect google`."
                ),
                exit_code=1,
            )

        file_id = str(arguments.get("file_id", "")).strip()
        if not file_id:
            return ToolResult(
                call_id=call_id,
                name=self.name,
                output="",
                error="Parameter 'file_id' cannot be empty.",
                exit_code=1,
            )

        max_bytes = int(arguments.get("max_bytes", 20000))
        try:
            api_client = self.client or GoogleDriveApiClient(access_token=token or "")
            content = api_client.read_file_content(file_id=file_id, max_bytes=max_bytes)
            return ToolResult(
                call_id=call_id,
                name=self.name,
                output=f"### Google Drive Document ({file_id}):\n\n{content}",
                exit_code=0,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                name=self.name,
                output="",
                error=f"Google Drive read error: {exc}",
                exit_code=1,
            )
