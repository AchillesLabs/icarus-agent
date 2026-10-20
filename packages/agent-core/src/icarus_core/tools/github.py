"""Native agent tools for GitHub repository inspection, issues, and pull requests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from icarus_contracts.tools import ToolDefinition, ToolResult, ToolSafetyCategory
from icarus_core.tools.auth import ToolAuthManager
from icarus_core.tools.base import BaseTool


class GithubIssuesTool(BaseTool):
    """Tool allowing the agent to list and search issues and pull requests on GitHub."""

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="github_issues",
            description="List and inspect issues or pull requests for a given GitHub repository.",
            parameters={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository in 'owner/repo' format (e.g. 'AchillesLabs/icarus-agent').",
                    },
                    "state": {
                        "type": "string",
                        "description": "Issue state ('open', 'closed', 'all', default: 'open').",
                        "enum": ["open", "closed", "all"],
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of issues to fetch (default: 5).",
                    },
                },
                "required": ["repo"],
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
        token = ToolAuthManager.get_token("github")
        if not token:
            token = ToolAuthManager.prompt_authorization("github")
            if not token:
                return ToolResult(
                    call_id=call_id,
                    name=self.name,
                    output="",
                    error=(
                        "GitHub authorization required. Please authorize your account with a Personal Access Token at "
                        "https://github.com/settings/tokens or run `/connect github`."
                    ),
                    exit_code=1,
                )

        repo = str(arguments.get("repo", "")).strip()
        state = str(arguments.get("state", "open")).strip()
        max_results = min(int(arguments.get("max_results", 5)), 20)

        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "IcarusAgent/0.1.0",
        }

        url = f"https://api.github.com/repos/{repo}/issues?state={state}&per_page={max_results}"

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    issues = resp.json()
                    if not issues:
                        return ToolResult(
                            call_id=call_id,
                            name=self.name,
                            output=f"No {state} issues found in {repo}.",
                            exit_code=0,
                        )

                    lines = [f"GitHub Issues for {repo} ({len(issues)} items):"]
                    for iss in issues:
                        number = iss.get("number")
                        title = iss.get("title")
                        user = iss.get("user", {}).get("login", "unknown")
                        is_pr = "pull_request" in iss
                        kind = "PR" if is_pr else "Issue"
                        lines.append(f"• [#{number}] ({kind}) {title} - by @{user}")

                    return ToolResult(call_id=call_id, name=self.name, output="\n".join(lines), exit_code=0)
                return ToolResult(
                    call_id=call_id,
                    name=self.name,
                    output="",
                    error=f"GitHub API returned error {resp.status_code}: {resp.text}",
                    exit_code=1,
                )
        except Exception as exc:
            return ToolResult(call_id=call_id, name=self.name, output="", error=f"GitHub request failed: {exc}", exit_code=1)


class GithubCreateIssueTool(BaseTool):
    """Tool allowing the agent to create an issue on GitHub with approval."""

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="github_create_issue",
            description="Create a new issue in a GitHub repository.",
            parameters={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository in 'owner/repo' format.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Issue title.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Detailed issue description/markdown.",
                    },
                },
                "required": ["repo", "title", "body"],
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
        token = ToolAuthManager.get_token("github")
        if not token:
            token = ToolAuthManager.prompt_authorization("github")
            if not token:
                return ToolResult(
                    call_id=call_id,
                    name=self.name,
                    output="",
                    error="GitHub authorization required. Please authorize at https://github.com/settings/tokens",
                    exit_code=1,
                )

        repo = arguments.get("repo", "").strip()
        title = arguments.get("title", "").strip()
        body = arguments.get("body", "").strip()

        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "IcarusAgent/0.1.0",
        }

        url = f"https://api.github.com/repos/{repo}/issues"
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(url, headers=headers, json={"title": title, "body": body})
                if resp.status_code == 201:
                    created = resp.json()
                    html_url = created.get("html_url")
                    num = created.get("number")
                    return ToolResult(
                        call_id=call_id,
                        name=self.name,
                        output=f"Successfully created GitHub issue #{num} in {repo}: {html_url}",
                        exit_code=0,
                    )
                return ToolResult(call_id=call_id, name=self.name, output="", error=f"GitHub issue creation failed ({resp.status_code}): {resp.text}", exit_code=1)
        except Exception as exc:
            return ToolResult(call_id=call_id, name=self.name, output="", error=f"GitHub request error: {exc}", exit_code=1)
