"""Unit and integration tests for CLI agent loop execution and Rich UI observers."""

import io
from pathlib import Path

from icarus_cli.observer import RichAgentObserver
from icarus_cli.run import execute_run
from icarus_contracts.tools import ToolCall, ToolResult
from icarus_core.providers.mock import MockProvider
from rich.console import Console


def test_rich_agent_observer_renders_tool_lifecycle():
    """RichAgentObserver formats tokens, tool start panels/spinners, and outcome summaries."""
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, color_system="standard")
    observer = RichAgentObserver(console=console)

    # 1. Token streaming
    observer.on_token("Thinking ")
    observer.on_token("about the task...")
    assert "Thinking about the task..." in buf.getvalue()

    # 2. Tool start
    tc = ToolCall(id="call_1", name="read_file", arguments={"path": "config.toml"})
    observer.on_tool_start(tc)
    output = buf.getvalue()
    assert "read_file" in output
    assert "config.toml" in output

    # 3. Successful tool end
    res_ok = ToolResult(
        call_id="call_1",
        name="read_file",
        output="[settings]\nkey = 'value'",
        exit_code=0,
    )
    observer.on_tool_end(res_ok)
    output = buf.getvalue()
    assert "completed" in output.lower() or "read_file" in output

    # 4. Failed/rejected tool end
    res_err = ToolResult(
        call_id="call_2",
        name="write_file",
        output="",
        error="Action rejected by user.",
        exit_code=1,
    )
    observer.on_tool_end(res_err)
    output = buf.getvalue()
    assert "rejected by user" in output or "failed" in output.lower()


def test_execute_run_end_to_end_with_autonomous_tool(tmp_path: Path, monkeypatch):
    """execute_run autonomously executes tools via AgentLoop and answers user prompt."""
    test_file = tmp_path / "pyproject.toml"
    test_file.write_text('[project]\nversion = "0.2.1"\n', encoding="utf-8")

    tc = ToolCall(id="c1", name="read_file", arguments={"path": "pyproject.toml"})
    mock_prov = MockProvider(
        responses=["The version is 0.2.1."],
        tool_calls_sequence=[[tc], None],
    )

    from icarus_core.providers.registry import ProviderRegistry

    monkeypatch.setattr(ProviderRegistry, "get_provider", lambda self, name: mock_prov)
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

    out_buf = io.StringIO()
    console_out = io.StringIO()
    console = Console(file=console_out, force_terminal=False)

    exit_code = execute_run(
        prompt="read pyproject.toml and tell me what the version is",
        provider_name="mock",
        console=console,
        stdout=out_buf,
        auto_approve=True,
    )

    assert exit_code == 0
    full_output = out_buf.getvalue() + console_out.getvalue()
    assert "read_file" in full_output
    assert "0.2.1" in full_output
    assert mock_prov.call_count == 2
