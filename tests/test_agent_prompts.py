"""Tests for dynamic agent persona and system prompt builder."""

from pathlib import Path
from unittest.mock import patch

from icarus_contracts.provider import PromptMessage
from icarus_contracts.session import MessageRole
from icarus_core.agent.prompts import (
    SystemPromptBuilder,
    build_system_prompt,
    inject_system_prompt,
)


def test_system_prompt_builder_contains_identity_and_guidelines():
    """System prompt contains Icarus identity, guidelines, and safety principles."""
    builder = SystemPromptBuilder()
    prompt = builder.build(cwd=Path("/workspace/project"), os_info="Linux 6.1.0", git_branch="main")

    assert "Icarus" in prompt
    assert "Linux 6.1.0" in prompt
    assert "/workspace/project" in prompt
    assert "main" in prompt
    assert "safety" in prompt.lower() or "guidelines" in prompt.lower()


def test_system_prompt_builder_dynamic_defaults(tmp_path: Path):
    """When cwd and os_info are omitted, builder resolves current runtime environment."""
    with patch("os.getcwd", return_value=str(tmp_path)):
        builder = SystemPromptBuilder()
        prompt = builder.build()

        assert tmp_path.as_posix() in prompt
        assert len(prompt) > 100


def test_build_system_prompt_convenience_function(tmp_path: Path):
    """build_system_prompt helper returns formatted system prompt string."""
    prompt = build_system_prompt(cwd=tmp_path, os_info="Windows 11")
    assert "Icarus" in prompt
    assert "Windows 11" in prompt


def test_inject_system_prompt_prepends_system_message():
    """inject_system_prompt adds a MessageRole.SYSTEM message to the front of prompt messages."""
    user_msg = PromptMessage(role=MessageRole.USER, content="Hello Icarus")
    messages = [user_msg]

    injected = inject_system_prompt(messages, cwd=Path("/test/workspace"), os_info="TestOS")

    # Original list unchanged
    assert len(messages) == 1
    assert messages[0].role == MessageRole.USER

    # Injected list has system message first
    assert len(injected) == 2
    assert injected[0].role == MessageRole.SYSTEM
    assert "Icarus" in injected[0].content
    assert "/test/workspace" in injected[0].content
    assert injected[1].role == MessageRole.USER
    assert injected[1].content == "Hello Icarus"


def test_inject_system_prompt_replaces_existing_system_message():
    """If a system prompt is already present at index 0, it is refreshed rather than duplicated."""
    old_system_msg = PromptMessage(role=MessageRole.SYSTEM, content="Old prompt")
    user_msg = PromptMessage(role=MessageRole.USER, content="Run a command")
    asst_msg = PromptMessage(role=MessageRole.ASSISTANT, content="Sure")
    messages = [old_system_msg, user_msg, asst_msg]

    injected = inject_system_prompt(messages, cwd=Path("/new/workspace"), os_info="TestOS")

    assert len(injected) == 3
    assert injected[0].role == MessageRole.SYSTEM
    assert "/new/workspace" in injected[0].content
    assert "Old prompt" not in injected[0].content
    assert injected[1] == user_msg
    assert injected[2] == asst_msg
