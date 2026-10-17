"""Workspace search tool: SearchTool with regex, literal, and glob filtering."""

from __future__ import annotations

import fnmatch
import json
import os
import re
from pathlib import Path
from typing import Any

from icarus_contracts.exceptions import WorkspaceJailError
from icarus_contracts.tools import ToolDefinition, ToolResult, ToolSafetyCategory

from icarus_core.tools.base import BaseTool
from icarus_core.tools.filesystem import NOISE_DIRS
from icarus_core.tools.security import resolve_workspace_path


def _matches_glob(rel_path: Path, pattern: str) -> bool:
    """Check if relative path matches a glob pattern."""
    posix_path = rel_path.as_posix()
    name = rel_path.name
    if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(posix_path, pattern):
        return True
    try:
        if rel_path.match(pattern):
            return True
    except Exception:
        pass
    return False


def _matches_any_glob(rel_path: Path, patterns: str | list[str] | Any) -> bool:
    """Check if relative path matches any of the glob patterns."""
    if isinstance(patterns, str):
        pattern_list = [p.strip() for p in patterns.replace(",", " ").split() if p.strip()]
    elif isinstance(patterns, (list, tuple, set)):
        pattern_list = [str(p).strip() for p in patterns if str(p).strip()]
    else:
        return False
    return any(_matches_glob(rel_path, p) for p in pattern_list)


class SearchTool(BaseTool):
    """Tool to search for text or regex pattern matches across files within the workspace."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="search",
            description=(
                "Search for text or regex pattern matches across files in the workspace with "
                "case sensitivity, glob filtering, and bounded results."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Text pattern or regular expression to search for",
                    },
                    "path": {
                        "type": "string",
                        "description": (
                            "Directory or file path relative to workspace root (default: '.')"
                        ),
                        "default": ".",
                    },
                    "regex": {
                        "type": "boolean",
                        "description": (
                            "Whether query should be evaluated as a regex pattern (default: false)"
                        ),
                        "default": False,
                    },
                    "case_sensitive": {
                        "type": "boolean",
                        "description": "Whether the search is case-sensitive (default: false)",
                        "default": False,
                    },
                    "include_pattern": {
                        "type": "string",
                        "description": (
                            "File glob pattern to include, e.g. '*.py' (default: all text files)"
                        ),
                    },
                    "exclude_pattern": {
                        "type": "string",
                        "description": "File glob pattern to exclude, e.g. '*.test.py'",
                    },
                    "max_matches": {
                        "type": "integer",
                        "description": "Maximum number of total matches to return (default: 50)",
                        "default": 50,
                    },
                },
                "required": ["query"],
            },
            safety_category=ToolSafetyCategory.SAFE_READ,
        )

    def execute(
        self,
        arguments: dict[str, Any],
        workspace_root: Path | str,
        call_id: str = "direct_call",
    ) -> ToolResult:
        query = str(arguments.get("query", "") or "").strip()
        if not query:
            return ToolResult(
                call_id=call_id,
                name="search",
                output="",
                error="Missing required argument 'query'.",
                exit_code=1,
            )

        root = Path(workspace_root).resolve()
        rel_path = str(arguments.get("path", ".") or ".").strip()

        try:
            target_path = resolve_workspace_path(rel_path, root)
        except WorkspaceJailError as exc:
            return ToolResult(
                call_id=call_id,
                name="search",
                output="",
                error=str(exc),
                exit_code=1,
            )

        if not target_path.exists():
            return ToolResult(
                call_id=call_id,
                name="search",
                output="",
                error=f"Path not found: '{rel_path}'.",
                exit_code=1,
            )

        case_sensitive = bool(arguments.get("case_sensitive", False))
        is_regex = bool(arguments.get("regex", False))
        raw_max = (
            arguments.get("max_matches")
            if arguments.get("max_matches") is not None
            else arguments.get("limit")
        )
        if raw_max is None:
            raw_max = arguments.get("max_results")
        max_matches = int(raw_max) if raw_max is not None else 50
        include_pattern = (
            arguments.get("include_pattern")
            or arguments.get("pattern")
            or arguments.get("file_pattern")
            or arguments.get("glob")
            or arguments.get("include_glob")
        )
        exclude_pattern = (
            arguments.get("exclude_pattern")
            or arguments.get("exclude_glob")
            or arguments.get("ignore_pattern")
        )

        flags = 0 if case_sensitive else re.IGNORECASE
        pattern_str = query if is_regex else re.escape(query)
        try:
            compiled_regex = re.compile(pattern_str, flags=flags)
        except re.error as exc:
            return ToolResult(
                call_id=call_id,
                name="search",
                output="",
                error=f"Invalid regular expression '{query}': {exc}",
                exit_code=1,
            )

        matches: list[dict[str, Any]] = []

        # Collect files to scan
        files_to_scan: list[Path] = []
        if target_path.is_file():
            files_to_scan.append(target_path)
        else:
            for current_root, dirs, files in os.walk(target_path):
                dirs[:] = [d for d in dirs if d not in NOISE_DIRS]
                for f in sorted(files):
                    files_to_scan.append(Path(current_root) / f)

        for file_path in files_to_scan:
            rel_file = file_path.relative_to(root)
            if include_pattern and not _matches_any_glob(rel_file, include_pattern):
                continue
            if exclude_pattern and _matches_any_glob(rel_file, exclude_pattern):
                continue

            if len(matches) >= max_matches:
                break

            try:
                raw_bytes = file_path.read_bytes()
                # Skip binary files
                if b"\x00" in raw_bytes[:1024]:
                    continue
                content = raw_bytes.decode("utf-8", errors="replace")
            except Exception:
                continue

            rel_file_posix = file_path.relative_to(root).as_posix()
            lines = content.splitlines()

            for line_idx, line in enumerate(lines, start=1):
                if compiled_regex.search(line):
                    matches.append(
                        {
                            "file": rel_file_posix,
                            "path": rel_file_posix,
                            "line_number": line_idx,
                            "line": line_idx,
                            "snippet": line.strip("\r\n"),
                        }
                    )
                    if len(matches) >= max_matches:
                        break

        return ToolResult(
            call_id=call_id,
            name="search",
            output=json.dumps(matches, indent=2),
            exit_code=0,
        )
