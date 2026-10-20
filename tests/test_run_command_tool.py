"""Tests for run_command tool: RunCommandTool."""

from pathlib import Path

from icarus_contracts.tools import ToolSafetyCategory
from icarus_core.tools import RunCommandTool
from icarus_core.tools.registry import create_default_registry


def test_run_command_tool_definition():
    """RunCommandTool must have metadata, schema, and REQUIRES_APPROVAL category."""
    tool = RunCommandTool()
    definition = tool.definition

    assert definition.name == "run_command"
    assert "command" in definition.description.lower()
    assert definition.safety_category == ToolSafetyCategory.REQUIRES_APPROVAL

    props = definition.parameters.get("properties", {})
    assert "command" in props
    assert props["command"]["type"] == "string"

    assert "timeout" in props
    assert props["timeout"]["type"] in ("number", "integer")

    assert "cwd" in props
    assert props["cwd"]["type"] == "string"

    assert definition.parameters.get("required") == ["command"]


def test_run_command_registered_in_default_registry():
    """Default ToolRegistry includes run_command."""
    registry = create_default_registry()
    assert registry.has("run_command")
    tool = registry.get("run_command")
    assert isinstance(tool, RunCommandTool)


def test_run_command_success(tmp_path: Path):
    """Successful command execution captures stdout with exit code 0."""
    tool = RunCommandTool()
    cmd = "python -c \"print('hello from icarus')\""
    result = tool.execute(
        arguments={"command": cmd},
        workspace_root=tmp_path,
        call_id="call_cmd_1",
    )

    assert result.call_id == "call_cmd_1"
    assert result.name == "run_command"
    assert result.exit_code == 0
    assert result.error is None
    assert "hello from icarus" in result.output


def test_run_command_nonzero_exit_captures_error_and_code(tmp_path: Path):
    """Non-zero exit code is recorded and stderr/stdout is captured."""
    tool = RunCommandTool()
    cmd = "python -c \"import sys; sys.stderr.write('err output\\n'); sys.exit(42)\""
    result = tool.execute(
        arguments={"command": cmd},
        workspace_root=tmp_path,
        call_id="call_cmd_err",
    )

    assert result.exit_code == 42
    assert "err output" in (result.error or "") or "err output" in result.output
    assert result.error is not None


def test_run_command_cwd_within_workspace(tmp_path: Path):
    """Command executes in the specified workspace subdirectory."""
    sub_dir = tmp_path / "subproject"
    sub_dir.mkdir()

    tool = RunCommandTool()
    cmd = 'python -c "from pathlib import Path; print(Path.cwd().name)"'
    result = tool.execute(
        arguments={"command": cmd, "cwd": "subproject"},
        workspace_root=tmp_path,
    )

    assert result.exit_code == 0
    assert "subproject" in result.output.strip()


def test_run_command_jail_escape_rejected(tmp_path: Path):
    """Attempting to set cwd outside workspace is rejected by workspace jail."""
    tool = RunCommandTool()
    result = tool.execute(
        arguments={"command": "echo test", "cwd": "../outside"},
        workspace_root=tmp_path,
    )

    assert result.exit_code == 1
    assert "escapes workspace boundary" in (result.error or "").lower()


def test_run_command_missing_command_argument(tmp_path: Path):
    """Missing or empty command argument returns error."""
    tool = RunCommandTool()
    res1 = tool.execute(arguments={}, workspace_root=tmp_path)
    assert res1.exit_code == 1
    assert "missing" in (res1.error or "").lower()

    res2 = tool.execute(arguments={"command": "   "}, workspace_root=tmp_path)
    assert res2.exit_code == 1
    assert "empty" in (res2.error or "").lower()


def test_run_command_timeout_enforced_and_kills_process(tmp_path: Path):
    """Execution exceeding timeout budget is aborted cleanly with non-zero exit code."""
    import time

    tool = RunCommandTool()
    cmd = 'python -c "import time; time.sleep(5)"'
    start = time.perf_counter()
    result = tool.execute(
        arguments={"command": cmd, "timeout": 0.3},
        workspace_root=tmp_path,
        call_id="call_timeout",
    )
    elapsed = time.perf_counter() - start

    assert elapsed < 3.0
    assert result.exit_code == 124
    assert result.error is not None
    assert "timed out after 0.3 seconds" in result.error


def test_run_command_interactive_approval_rejection_prevents_execution(tmp_path: Path):
    """Rejection during interactive approval returns clean refusal without executing command."""
    from icarus_contracts.tools import ToolCall
    from icarus_core.agent.approvals import ApprovalEngine, ApprovalPolicy

    tool = RunCommandTool()
    canary_file = tmp_path / "should_not_exist.txt"
    cmd = f"python -c \"from pathlib import Path; Path(r'{canary_file}').write_text('executed')\""

    engine = ApprovalEngine(
        policy=ApprovalPolicy.INTERACTIVE,
        prompt_callback=lambda call, defn: False,
    )

    call = ToolCall(id="call_run_cmd", name="run_command", arguments={"command": cmd})
    result = engine.execute_with_approval(call, tool, workspace_root=tmp_path)

    assert result.exit_code == 1
    assert "rejected" in result.error.lower()
    assert not canary_file.exists()


def test_run_command_interactive_approval_acceptance_executes(tmp_path: Path):
    """Approval during interactive prompt executes the command."""
    from icarus_contracts.tools import ToolCall
    from icarus_core.agent.approvals import ApprovalEngine, ApprovalPolicy

    tool = RunCommandTool()
    canary_file = tmp_path / "created.txt"
    cmd = f"python -c \"from pathlib import Path; Path(r'{canary_file}').write_text('ok')\""

    engine = ApprovalEngine(
        policy=ApprovalPolicy.INTERACTIVE,
        prompt_callback=lambda call, defn: True,
    )

    call = ToolCall(id="call_run_cmd", name="run_command", arguments={"command": cmd})
    result = engine.execute_with_approval(call, tool, workspace_root=tmp_path)

    assert result.exit_code == 0
    assert result.error is None
    assert canary_file.exists()
    assert canary_file.read_text() == "ok"


def test_run_command_auto_approve_policy(tmp_path: Path):
    """Auto-approve policy permits command execution without interactive callback."""
    from icarus_contracts.tools import ToolCall
    from icarus_core.agent.approvals import ApprovalEngine, ApprovalPolicy

    tool = RunCommandTool()
    call = ToolCall(
        id="call_auto",
        name="run_command",
        arguments={"command": "python -c \"print('auto ok')"},
    )
    engine = ApprovalEngine(policy=ApprovalPolicy.AUTO_APPROVE)
    decision = engine.evaluate(call, tool.definition)
    assert decision.approved is True


def test_run_command_hosted_mode_fails_closed(tmp_path: Path):
    """In hosted mode without an isolated sandbox, host shell execution must be blocked."""
    tool = RunCommandTool(hosted_mode=True)
    result = tool.execute({"command": "echo 'host breach'"}, workspace_root=tmp_path)

    assert result.exit_code == 1
    assert "Host shell execution is disabled in hosted API mode" in result.error


def test_run_command_isolated_sandbox_permitted_in_hosted_mode(tmp_path: Path):
    """An isolated sandbox backend executes successfully in hosted mode."""
    from icarus_core.tools.command import CommandSandboxBackend

    class DummyIsolatedSandbox(CommandSandboxBackend):
        @property
        def is_isolated(self) -> bool:
            return True

        async def run(
            self,
            cmd_args: list[str],
            working_dir: Path,
            timeout: float,
            max_output_bytes: int = 100_000,
        ) -> tuple[int, str, str]:
            return 0, "sandbox container stdout output", ""

    tool = RunCommandTool(hosted_mode=True, sandbox=DummyIsolatedSandbox())
    result = tool.execute({"command": "ls -la"}, workspace_root=tmp_path)

    assert result.exit_code == 0
    assert "sandbox container stdout output" in result.output
