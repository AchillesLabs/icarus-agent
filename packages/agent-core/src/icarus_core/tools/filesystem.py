"""Filesystem inspection tools: read_file and list_dir."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from icarus_contracts.exceptions import WorkspaceJailError
from icarus_contracts.tools import ToolDefinition, ToolResult, ToolSafetyCategory

from icarus_core.tools.base import BaseTool
from icarus_core.tools.security import resolve_workspace_path

NOISE_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
}


class ReadFileTool(BaseTool):
    """Tool to read the contents of a file within the workspace with line offset/limit."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_file",
            description=(
                "Read text content of a file within the workspace with line "
                "offset and limit controls."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to the workspace root",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "1-indexed line number to start reading from (default: 1)",
                        "default": 1,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of lines to return (default: 500)",
                        "default": 500,
                    },
                },
                "required": ["path"],
            },
            safety_category=ToolSafetyCategory.SAFE_READ,
        )

    def execute(
        self,
        arguments: dict[str, Any],
        workspace_root: Path | str,
        call_id: str = "direct_call",
    ) -> ToolResult:
        rel_path = str(arguments.get("path", "")).strip()
        if not rel_path:
            return ToolResult(
                call_id=call_id,
                name="read_file",
                output="",
                error="Missing required argument 'path'.",
                exit_code=1,
            )

        try:
            target_file = resolve_workspace_path(rel_path, workspace_root)
        except WorkspaceJailError as exc:
            return ToolResult(
                call_id=call_id,
                name="read_file",
                output="",
                error=str(exc),
                exit_code=1,
            )

        if not target_file.exists():
            return ToolResult(
                call_id=call_id,
                name="read_file",
                output="",
                error=f"File not found: '{rel_path}'.",
                exit_code=1,
            )

        if target_file.is_dir():
            return ToolResult(
                call_id=call_id,
                name="read_file",
                output="",
                error=f"Path '{rel_path}' is a directory. Use list_dir to inspect directories.",
                exit_code=1,
            )

        try:
            raw_bytes = target_file.read_bytes()
            if b"\x00" in raw_bytes[:1024]:
                return ToolResult(
                    call_id=call_id,
                    name="read_file",
                    output=f"Binary file ({len(raw_bytes)} bytes) cannot be displayed as text.",
                    exit_code=0,
                )
            content = raw_bytes.decode("utf-8", errors="replace")
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                name="read_file",
                output="",
                error=f"Failed to read file '{rel_path}': {exc}",
                exit_code=1,
            )

        lines = content.splitlines()
        if not lines:
            return ToolResult(
                call_id=call_id,
                name="read_file",
                output="(File is empty)",
                exit_code=0,
            )

        offset = int(arguments.get("offset", 1) or 1)
        raw_limit = arguments.get("limit")
        limit = int(raw_limit) if raw_limit is not None else 500

        if offset > len(lines):
            return ToolResult(
                call_id=call_id,
                name="read_file",
                output=f"(Offset {offset} is beyond file length of {len(lines)} lines)",
                exit_code=0,
            )

        start_idx = max(0, offset - 1)
        end_idx = start_idx + limit if limit > 0 else len(lines)
        sliced_lines = lines[start_idx:end_idx]

        formatted = "\n".join(
            f"{start_idx + idx + 1}: {line}" for idx, line in enumerate(sliced_lines)
        )
        return ToolResult(
            call_id=call_id,
            name="read_file",
            output=formatted,
            exit_code=0,
        )


class ListDirTool(BaseTool):
    """Tool to inspect directories within the workspace with entry type and size metadata."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="list_dir",
            description="List directory contents within the workspace with entry type and size.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path relative to workspace root (default: '.')",
                        "default": ".",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": (
                            "Whether to list subdirectories recursively (default: false)"
                        ),
                        "default": False,
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": (
                            "Maximum recursion depth when recursive is true (default: 2)"
                        ),
                        "default": 2,
                    },
                },
                "required": [],
            },
            safety_category=ToolSafetyCategory.SAFE_READ,
        )

    def execute(
        self,
        arguments: dict[str, Any],
        workspace_root: Path | str,
        call_id: str = "direct_call",
    ) -> ToolResult:
        rel_path = str(arguments.get("path", ".") or ".").strip()
        recursive = bool(arguments.get("recursive", False))
        max_depth = int(arguments.get("max_depth", 2) or 2)

        root = Path(workspace_root).resolve()
        try:
            target_dir = resolve_workspace_path(rel_path, root)
        except WorkspaceJailError as exc:
            return ToolResult(
                call_id=call_id,
                name="list_dir",
                output="",
                error=str(exc),
                exit_code=1,
            )

        if not target_dir.exists():
            return ToolResult(
                call_id=call_id,
                name="list_dir",
                output="",
                error=f"Directory not found: '{rel_path}'.",
                exit_code=1,
            )

        if not target_dir.is_dir():
            return ToolResult(
                call_id=call_id,
                name="list_dir",
                output="",
                error=f"Path '{rel_path}' is not a directory. Use read_file to read files.",
                exit_code=1,
            )

        entries: list[dict[str, Any]] = []

        if not recursive:
            try:
                sorted_entries = sorted(
                    target_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())
                )
                for entry in sorted_entries:
                    if entry.name in NOISE_DIRS:
                        continue
                    is_dir = entry.is_dir()
                    size_bytes = 0 if is_dir else entry.stat().st_size
                    rel_to_ws = entry.relative_to(root).as_posix()
                    entries.append(
                        {
                            "name": entry.name,
                            "path": rel_to_ws,
                            "is_dir": is_dir,
                            "size_bytes": size_bytes,
                        }
                    )
            except Exception as exc:
                return ToolResult(
                    call_id=call_id,
                    name="list_dir",
                    output="",
                    error=f"Failed to list directory '{rel_path}': {exc}",
                    exit_code=1,
                )
        else:
            base_depth = len(target_dir.parts)
            for current_root, dirs, files in os.walk(target_dir):
                current_path = Path(current_root)
                depth = len(current_path.parts) - base_depth
                # Prune noise directories in-place
                dirs[:] = [d for d in dirs if d not in NOISE_DIRS]
                if depth >= max_depth:
                    dirs.clear()

                for d in sorted(dirs):
                    dir_path = current_path / d
                    entries.append(
                        {
                            "name": d,
                            "path": dir_path.relative_to(root).as_posix(),
                            "is_dir": True,
                            "size_bytes": 0,
                        }
                    )

                for f in sorted(files):
                    file_path = current_path / f
                    try:
                        size = file_path.stat().st_size
                    except Exception:
                        size = 0
                    entries.append(
                        {
                            "name": f,
                            "path": file_path.relative_to(root).as_posix(),
                            "is_dir": False,
                            "size_bytes": size,
                        }
                    )

        return ToolResult(
            call_id=call_id,
            name="list_dir",
            output=json.dumps(entries, indent=2),
            exit_code=0,
        )
