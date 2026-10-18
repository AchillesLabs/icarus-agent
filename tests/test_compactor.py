"""Unit tests for Turn-Boundary History Compactor and Tool Pairing Protection."""

import pytest
from icarus_contracts import (
    CompactionResult,
    MessageRole,
    PromptMessage,
    ToolCall,
)
from icarus_core.agent.compactor import HistoryCompactor
from icarus_core.tokens import HeuristicTokenCounter


@pytest.fixture
def sample_tool_turn_history() -> list[PromptMessage]:
    """A realistic 3-turn conversation history with tool executions."""
    return [
        PromptMessage(role=MessageRole.USER, content="Please inspect and test the auth module."),
        PromptMessage(
            role=MessageRole.ASSISTANT,
            content="I will read the auth file.",
            tool_calls=[
                ToolCall(id="call_read_1", name="read_file", arguments={"path": "src/auth.py"})
            ],
        ),
        PromptMessage(
            role=MessageRole.TOOL,
            content="def authenticate(user, password): return True",
            name="read_file",
            tool_call_id="call_read_1",
        ),
        PromptMessage(
            role=MessageRole.ASSISTANT,
            content="Now I will run the test suite.",
            tool_calls=[
                ToolCall(
                    id="call_cmd_1",
                    name="run_command",
                    arguments={"command": "pytest tests/test_auth.py"},
                )
            ],
        ),
        PromptMessage(
            role=MessageRole.TOOL,
            content="1 passed in 0.05s",
            name="run_command",
            tool_call_id="call_cmd_1",
        ),
        PromptMessage(role=MessageRole.ASSISTANT, content="All auth tests pass."),
        PromptMessage(role=MessageRole.USER, content="Great, what should we do next?"),
        PromptMessage(role=MessageRole.ASSISTANT, content="We can proceed to phase 3."),
    ]


# --- Seam 1: Tool Pairing Protection ---


def test_safe_cut_index_never_splits_tool_call_and_tool_result(sample_tool_turn_history):
    """Verify cut index never separates an assistant tool_calls message from tool results."""
    compactor = HistoryCompactor()

    # Index 2 is the Tool result for call_read_1 (assistant message is index 1).
    # Cutting at 2 would put assistant at [:2] and tool result at [2:].
    # Compactor must adjust cut so the tool pair is not severed.
    safe_cut = compactor.find_safe_cut_index(sample_tool_turn_history, target_retained_count=6)
    # The cut must either include both in compacted (cut >= 3) or keep both in retained (cut <= 1)
    assert safe_cut in (0, 1, 3, 5, 6)
    assert safe_cut != 2  # Cannot cut right after assistant tool call before tool result


def test_retained_messages_never_start_with_orphaned_tool_message(sample_tool_turn_history):
    """Verify that retained messages never begin with a tool role message."""
    compactor = HistoryCompactor()

    for target_retained in range(1, len(sample_tool_turn_history)):
        cut = compactor.find_safe_cut_index(
            sample_tool_turn_history, target_retained_count=target_retained
        )
        if cut < len(sample_tool_turn_history):
            first_retained = sample_tool_turn_history[cut]
            assert first_retained.role != MessageRole.TOOL, (
                f"Cut {cut} produced orphaned tool message in retained history"
            )


# --- Seam 2: Turn Boundary Partitioning ---


def test_partition_history_clean_boundaries(sample_tool_turn_history):
    """Verify partition_history splits history at a clean turn boundary."""
    compactor = HistoryCompactor(min_retained_turns=1)

    compacted, retained = compactor.partition_history(
        sample_tool_turn_history, target_retained_turns=1
    )
    assert len(compacted) > 0
    assert len(retained) > 0
    assert len(compacted) + len(retained) == len(sample_tool_turn_history)

    # Retained messages start with a user turn or clean assistant answer
    assert retained[0].role in (MessageRole.USER, MessageRole.ASSISTANT)
    if retained[0].role == MessageRole.ASSISTANT:
        assert not retained[0].tool_calls or len(retained) > 1


def test_no_compaction_when_history_too_short():
    """Verify compactor skips compaction if history does not exceed min_retained_turns."""
    compactor = HistoryCompactor(min_retained_turns=2)
    short_history = [
        PromptMessage(role=MessageRole.USER, content="Hello"),
        PromptMessage(role=MessageRole.ASSISTANT, content="Hi there"),
    ]
    res = compactor.compact(short_history)
    assert res.original_message_count == 2
    assert res.compacted_message_count == 2
    assert len(res.compacted_messages) == 0
    assert len(res.retained_messages) == 2
    assert res.tokens_saved == 0


# --- Seam 3: Structured Markdown Summary ---


def test_format_summary_captures_intent_tools_and_files(sample_tool_turn_history):
    """Verify summary captures original task, tools called, and file modifications."""
    compactor = HistoryCompactor()
    compacted_part = sample_tool_turn_history[:6]

    summary = compactor.format_summary(compacted_part)

    # Check key schema sections
    assert "## [Previous Conversation Summary]" in summary
    assert "### Original Task Goal" in summary
    assert "inspect and test the auth module" in summary
    assert "### Key Decisions & Actions" in summary
    assert "### Touched Files & Commands" in summary
    assert "src/auth.py" in summary
    assert "pytest tests/test_auth.py" in summary
    assert "### Key Tool Results" in summary


# --- Seam 4: CompactionResult Telemetry & Verification ---


def test_compact_result_telemetry(sample_tool_turn_history):
    """Verify CompactionResult accurately reports token savings and counts."""
    # Simulate realistic heavy tool output (e.g. large file read dump)
    sample_tool_turn_history[2].content = (
        "def authenticate(user, password):\n    # Long code\n" * 50
    )
    counter = HeuristicTokenCounter(chars_per_token=4.0)
    compactor = HistoryCompactor(token_counter=counter, min_retained_turns=1)

    result = compactor.compact(sample_tool_turn_history, target_retained_turns=1)

    assert isinstance(result, CompactionResult)
    assert result.original_message_count == len(sample_tool_turn_history)
    assert result.compacted_message_count < result.original_message_count
    assert len(result.compacted_messages) > 0
    assert len(result.retained_messages) > 0
    assert result.tokens_before > 0
    assert result.tokens_after > 0
    assert result.tokens_saved > 0
    assert result.summary_message.role == MessageRole.SYSTEM
    assert "## [Previous Conversation Summary]" in (result.summary_message.content or "")


def test_compacted_messages_form_valid_provider_sequence(sample_tool_turn_history):
    """Verify that replacing compacted messages with summary yields a valid sequence."""
    compactor = HistoryCompactor(min_retained_turns=1)
    result = compactor.compact(sample_tool_turn_history, target_retained_turns=1)

    # Reconstructed prompt payload
    payload = [result.summary_message] + result.retained_messages

    assert payload[0].role == MessageRole.SYSTEM
    assert payload[1].role != MessageRole.TOOL  # No orphaned tool call
    # Tool call pairing invariant in payload
    for i, msg in enumerate(payload):
        if msg.role == MessageRole.TOOL:
            assert i > 0
            assert payload[i - 1].role == MessageRole.ASSISTANT
            assert payload[i - 1].tool_calls is not None
