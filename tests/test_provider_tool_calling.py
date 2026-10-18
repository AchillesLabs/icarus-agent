"""Tests for provider contracts and MockProvider tool calling capabilities."""

import pytest
from icarus_contracts.provider import CompletionResult, PromptMessage, StreamChunk
from icarus_contracts.session import MessageRole
from icarus_contracts.tools import ToolCall, ToolResult
from icarus_core.providers.mock import MockProvider


def test_prompt_message_tool_fields():
    """PromptMessage preserves tool_call_id and tool_calls attributes."""
    tool_call = ToolCall(id="call_123", name="read_file", arguments={"path": "pyproject.toml"})
    assistant_msg = PromptMessage(
        role=MessageRole.ASSISTANT,
        content="",
        tool_calls=[tool_call],
    )
    assert assistant_msg.tool_calls is not None
    assert len(assistant_msg.tool_calls) == 1
    assert assistant_msg.tool_calls[0].name == "read_file"

    tool_msg = PromptMessage(
        role=MessageRole.TOOL,
        content="file contents",
        name="read_file",
        tool_call_id="call_123",
    )
    assert tool_msg.tool_call_id == "call_123"


def test_tool_result_to_prompt_message_includes_tool_call_id():
    """ToolResult.to_prompt_message sets tool_call_id from call_id."""
    res = ToolResult(
        call_id="call_abc",
        name="read_file",
        output="version = 0.1.0",
        exit_code=0,
    )
    msg = res.to_prompt_message()
    assert msg.role == MessageRole.TOOL
    assert msg.name == "read_file"
    assert msg.content == "version = 0.1.0"
    assert msg.tool_call_id == "call_abc"


def test_stream_chunk_and_completion_result_tool_calls():
    """StreamChunk and CompletionResult hold tool_calls and deltas."""
    tc = ToolCall(id="c1", name="list_dir", arguments={"path": "."})
    chunk = StreamChunk(delta="", finish_reason="tool_calls", tool_calls=[tc])
    assert chunk.tool_calls == [tc]

    comp = CompletionResult(
        content="",
        model="mock-model",
        finish_reason="tool_calls",
        tool_calls=[tc],
    )
    assert comp.tool_calls == [tc]


@pytest.mark.asyncio
async def test_mock_provider_can_yield_tool_calls_stream():
    """MockProvider can be configured to yield tool calls in stream mode."""
    tc = ToolCall(id="call_1", name="read_file", arguments={"path": "README.md"})
    provider = MockProvider(
        responses=["Final answer after tool."],
        tool_calls_sequence=[[tc], None],  # Turn 1: tool call, Turn 2: no tool call (text)
    )

    chunks = []
    async for chunk in provider.stream(
        messages=[PromptMessage(role=MessageRole.USER, content="Read README.md")]
    ):
        chunks.append(chunk)

    # First turn yields tool call chunk
    tool_chunks = [c for c in chunks if c.tool_calls]
    assert len(tool_chunks) == 1
    assert tool_chunks[0].tool_calls[0].name == "read_file"
    assert tool_chunks[0].tool_calls[0].id == "call_1"


@pytest.mark.asyncio
async def test_mock_provider_can_return_tool_calls_generate():
    """MockProvider can return tool calls in generate mode."""
    tc = ToolCall(id="call_2", name="search", arguments={"pattern": "version"})
    provider = MockProvider(
        responses=["Found version."],
        tool_calls_sequence=[[tc], None],
    )

    res = await provider.generate(
        messages=[PromptMessage(role=MessageRole.USER, content="Search version")]
    )
    assert len(res.tool_calls) == 1
    assert res.tool_calls[0].name == "search"
    assert res.finish_reason == "tool_calls"


def test_provider_format_messages_with_tool_calls():
    """GroqProvider._format_messages converts tool messages and assistant tool calls."""
    from icarus_core.providers.groq import GroqProvider

    provider = GroqProvider(api_key="gsk_test")
    tc = ToolCall(id="call_x", name="read_file", arguments={"path": "pyproject.toml"})
    messages = [
        PromptMessage(role=MessageRole.USER, content="Check version"),
        PromptMessage(role=MessageRole.ASSISTANT, content=None, tool_calls=[tc]),
        PromptMessage(
            role=MessageRole.TOOL,
            content="[project]\nversion = '0.1.0'",
            name="read_file",
            tool_call_id="call_x",
        ),
    ]
    formatted = provider._format_messages(messages)
    assert len(formatted) == 3
    assert formatted[1]["role"] == "assistant"
    assert "tool_calls" in formatted[1]
    assert formatted[1]["tool_calls"][0]["id"] == "call_x"
    assert formatted[1]["tool_calls"][0]["function"]["name"] == "read_file"
    assert formatted[2]["role"] == "tool"
    assert formatted[2]["tool_call_id"] == "call_x"
    assert formatted[2]["content"] == "[project]\nversion = '0.1.0'"


@pytest.mark.asyncio
async def test_groq_streaming_parses_tool_call_deltas():
    """GroqProvider.stream parses multi-chunk SSE tool_calls deltas."""
    import httpx
    from icarus_core.providers.groq import GroqProvider

    chunk_1 = (
        'data: {"choices": [{"index": 0, "delta": {"tool_calls": '
        '[{"index": 0, "id": "call_99", "type": "function", "function": '
        '{"name": "read_file", "arguments": "{\\"path\\": "}}]}, "finish_reason": null}]}\n\n'
    )
    chunk_2 = (
        'data: {"choices": [{"index": 0, "delta": {"tool_calls": '
        '[{"index": 0, "function": {"arguments": "\\"pyproject.toml\\"}"}}]}, '
        '"finish_reason": "tool_calls"}], '
        '"usage": {"prompt_tokens": 12, "completion_tokens": 8}}\n\n'
    )
    sse_lines = [chunk_1, chunk_2, "data: [DONE]\n\n"]

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="".join(sse_lines),
            headers={"Content-Type": "text/event-stream"},
        )

    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)
    provider = GroqProvider(api_key="gsk_test", client=client)

    chunks = []
    async for chunk in provider.stream(
        messages=[PromptMessage(role=MessageRole.USER, content="Read version")],
        tools=[{"type": "function", "function": {"name": "read_file"}}],
    ):
        chunks.append(chunk)

    # Final chunk has finish_reason="tool_calls" and accumulated tool_calls
    tool_chunks = [c for c in chunks if c.tool_calls]
    assert len(tool_chunks) >= 1
    final_tool_chunk = tool_chunks[-1]
    assert len(final_tool_chunk.tool_calls) == 1
    tc = final_tool_chunk.tool_calls[0]
    assert tc.id == "call_99"
    assert tc.name == "read_file"
    assert tc.get_arguments_dict() == {"path": "pyproject.toml"}
