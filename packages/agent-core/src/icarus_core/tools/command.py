"""Tool for sandboxed shell and terminal command execution with timeout controls."""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import contextlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from icarus_contracts.exceptions import WorkspaceJailError
from icarus_contracts.tools import ToolDefinition, ToolResult, ToolSafetyCategory

from icarus_core.tools.base import BaseTool
from icarus_core.tools.security import resolve_workspace_path


def _build_powershell_args(command: str, exe: str) -> list[str]:
    """Construct PowerShell execution args preserving quotes and propagating native exit code."""
    script = f"{command}\nif ($LASTEXITCODE -ne $null) {{ exit $LASTEXITCODE }}"
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    return [
        exe,
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-EncodedCommand",
        encoded,
    ]


def resolve_shell_args(command: str, shell: str | None = None) -> list[str]:
    """Determine shell executable and arguments based on OS or explicit configuration."""
    normalized = (shell or "").strip().lower()

    if normalized in ("powershell", "pwsh"):
        exe = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
        return _build_powershell_args(command, exe)
    if normalized == "cmd":
        exe = shutil.which("cmd") or "cmd.exe"
        return [exe, "/d", "/c", command]
    if normalized == "bash":
        exe = shutil.which("bash") or "/bin/bash"
        return [exe, "-c", command]
    if normalized == "sh":
        exe = shutil.which("sh") or "/bin/sh"
        return [exe, "-c", command]
    if normalized:
        return [normalized, "-c", command]

    # Auto-detect default shell based on OS
    if sys.platform == "win32":
        # On Windows, powershell is preferred; fall back to cmd if unavailable
        pwsh = shutil.which("powershell") or shutil.which("pwsh")
        if pwsh:
            return _build_powershell_args(command, pwsh)
        cmd = shutil.which("cmd") or "cmd.exe"
        return [cmd, "/d", "/c", command]

    # On Unix, bash is preferred; fall back to sh
    bash = shutil.which("bash") or "/bin/bash"
    if os.path.exists(bash):
        return [bash, "-c", command]
    sh = shutil.which("sh") or "/bin/sh"
    return [sh, "-c", command]


class RunCommandTool(BaseTool):
    """Tool enabling the agent to execute shell commands within the workspace directory."""

    def __init__(self, default_shell: str | None = None) -> None:
        self.default_shell = default_shell

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="run_command",
            description=(
                "Execute a shell command strictly within the workspace directory "
                "with configurable timeout controls."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell or terminal command to execute.",
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Execution timeout budget in seconds (default: 30.0).",
                        "default": 30.0,
                    },
                    "cwd": {
                        "type": "string",
                        "description": (
                            "Working directory relative to the workspace root (default: '.')."
                        ),
                        "default": ".",
                    },
                    "shell": {
                        "type": "string",
                        "description": (
                            "Optional shell to use (e.g. 'powershell', 'cmd', 'bash', 'sh')."
                        ),
                    },
                },
                "required": ["command"],
            },
            safety_category=ToolSafetyCategory.REQUIRES_APPROVAL,
        )

    async def execute_async(
        self,
        arguments: dict[str, Any],
        workspace_root: Path | str,
        call_id: str = "direct_call",
    ) -> ToolResult:
        """Asynchronously execute the shell command with timeout controls."""
        if "command" not in arguments or arguments.get("command") is None:
            return ToolResult(
                call_id=call_id,
                name="run_command",
                output="",
                error="Missing required argument 'command'.",
                exit_code=1,
            )

        command = str(arguments["command"])
        if not command.strip():
            return ToolResult(
                call_id=call_id,
                name="run_command",
                output="",
                error="Argument 'command' cannot be empty.",
                exit_code=1,
            )

        timeout_arg = arguments.get("timeout", 30.0)
        try:
            timeout = float(timeout_arg) if timeout_arg is not None else 30.0
        except (ValueError, TypeError):
            timeout = 30.0

        rel_cwd = str(arguments.get("cwd", ".")).strip() or "."
        try:
            working_dir = resolve_workspace_path(rel_cwd, workspace_root)
        except WorkspaceJailError as exc:
            return ToolResult(
                call_id=call_id,
                name="run_command",
                output="",
                error=str(exc),
                exit_code=1,
            )

        if not working_dir.exists() or not working_dir.is_dir():
            return ToolResult(
                call_id=call_id,
                name="run_command",
                output="",
                error=f"Working directory '{rel_cwd}' does not exist or is not a directory.",
                exit_code=1,
            )

        shell_pref = arguments.get("shell") or self.default_shell
        cmd_args = resolve_shell_args(command, shell_pref)

        kwargs: dict[str, Any] = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "cwd": str(working_dir),
        }
        if sys.platform != "win32":
            kwargs["start_new_session"] = True

        try:
            process = await asyncio.create_subprocess_exec(*cmd_args, **kwargs)
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                name="run_command",
                output="",
                error=f"Failed to spawn process: {exc}",
                exit_code=1,
            )

        try:
            stdout_data, stderr_data = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
        except TimeoutError:
            # Cleanly terminate runaway process
            if sys.platform == "win32":
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                        capture_output=True,
                        timeout=5,
                    )
                except Exception:
                    with contextlib.suppress(Exception):
                        process.kill()
            else:
                try:
                    import signal

                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except Exception:
                    with contextlib.suppress(Exception):
                        process.kill()

            with contextlib.suppress(Exception):
                await asyncio.wait_for(process.wait(), timeout=2.0)

            return ToolResult(
                call_id=call_id,
                name="run_command",
                output="",
                error=f"Command execution timed out after {timeout} seconds.",
                exit_code=124,
            )

        stdout_str = stdout_data.decode("utf-8", errors="replace")
        stderr_str = stderr_data.decode("utf-8", errors="replace")

        if stdout_str and stderr_str:
            combined_output = f"{stdout_str}\n{stderr_str}".strip()
        elif stdout_str:
            combined_output = stdout_str.strip()
        elif stderr_str:
            combined_output = stderr_str.strip()
        else:
            combined_output = ""

        returncode = process.returncode or 0
        error_msg = None
        if returncode != 0:
            error_msg = (
                stderr_str.strip()
                if stderr_str.strip()
                else f"Command exited with non-zero status code {returncode}."
            )

        return ToolResult(
            call_id=call_id,
            name="run_command",
            output=combined_output,
            error=error_msg,
            exit_code=returncode,
        )

    def execute(
        self,
        arguments: dict[str, Any],
        workspace_root: Path | str,
        call_id: str = "direct_call",
    ) -> ToolResult:
        """Execute the tool synchronously within workspace root."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(
                    lambda: asyncio.run(self.execute_async(arguments, workspace_root, call_id))
                ).result()
        else:
            return asyncio.run(self.execute_async(arguments, workspace_root, call_id))
