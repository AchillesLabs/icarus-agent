"""Unit tests for token counting engine, token usage contracts, and provider estimators."""

from unittest.mock import patch

from icarus_contracts import (
    MessageCreate,
    MessageDTO,
    MessageRole,
    PromptMessage,
    ToolCall,
    ToolDefinition,
    ToolSafetyCategory,
)
from icarus_contracts.tokens import TokenUsage
from icarus_core.tokens import (
    HeuristicTokenCounter,
    TiktokenCounter,
    TokenCounter,
    count_tokens,
    get_token_counter,
)

# --- Seam 1: TokenUsage Contract ---


def test_token_usage_initialization_and_auto_total():
    """Verify TokenUsage defaults and automatic total_tokens calculation."""
    usage = TokenUsage(prompt_tokens=10, completion_tokens=25)
    assert usage.prompt_tokens == 10
    assert usage.completion_tokens == 25
    assert usage.total_tokens == 35

    explicit = TokenUsage(prompt_tokens=10, completion_tokens=25, total_tokens=40)
    assert explicit.total_tokens == 40


def test_token_usage_addition():
    """Verify TokenUsage addition and aggregation."""
    u1 = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    u2 = TokenUsage(prompt_tokens=20, completion_tokens=30, total_tokens=50)

    combined = u1 + u2
    assert combined.prompt_tokens == 30
    assert combined.completion_tokens == 35
    assert combined.total_tokens == 65

    combined_method = u1.add(u2)
    assert combined_method.total_tokens == 65


# --- Seam 2: HeuristicTokenCounter ---


def test_heuristic_counter_raw_text():
    """Verify HeuristicTokenCounter estimates tokens based on character length (~4 chars/tok)."""
    counter = HeuristicTokenCounter(chars_per_token=4.0)

    assert counter.count_text("") == 0
    assert counter.count_text(None) == 0
    # "Hello" is 5 chars -> ceil(5/4) = 2
    assert counter.count_text("Hello") == 2
    # 16 chars -> 4 tokens
    assert counter.count_text("1234567890123456") == 4


def test_heuristic_counter_message_and_role_overhead():
    """Verify HeuristicTokenCounter includes role overhead and content in message count."""
    counter = HeuristicTokenCounter(chars_per_token=4.0, role_overhead=4)

    msg = PromptMessage(role=MessageRole.USER, content="Hello")
    # 4 overhead + 2 content = 6 tokens
    assert counter.count_message(msg) == 6

    # Message with name
    msg_named = PromptMessage(role=MessageRole.USER, content="Hello", name="Alice")
    # 4 overhead + 2 ("Hello") + 2 ("Alice") + 1 = 9 tokens
    assert counter.count_message(msg_named) == 9


def test_heuristic_counter_message_with_tool_calls():
    """Verify HeuristicTokenCounter counts tool calls in assistant messages."""
    counter = HeuristicTokenCounter(chars_per_token=4.0)

    tc = ToolCall(id="call_123", name="read_file", arguments={"path": "main.py"})
    msg = PromptMessage(
        role=MessageRole.ASSISTANT,
        content="I will read the file.",
        tool_calls=[tc],
    )
    tokens = counter.count_message(msg)
    assert tokens > counter.count_text("I will read the file.") + 4


def test_heuristic_counter_messages_sequence():
    """Verify HeuristicTokenCounter sums messages and adds conversation overhead."""
    counter = HeuristicTokenCounter(conversation_overhead=3)

    assert counter.count_messages([]) == 0

    msgs = [
        PromptMessage(role=MessageRole.SYSTEM, content="System prompt"),
        PromptMessage(role=MessageRole.USER, content="User question"),
    ]
    expected = counter.count_message(msgs[0]) + counter.count_message(msgs[1]) + 3
    assert counter.count_messages(msgs) == expected


def test_heuristic_counter_tool_definition():
    """Verify HeuristicTokenCounter calculates tokens for ToolDefinition and dict schemas."""
    counter = HeuristicTokenCounter()

    tool = ToolDefinition(
        name="write_file",
        description="Write text to file",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
        safety_category=ToolSafetyCategory.REQUIRES_APPROVAL,
    )
    tok_tool = counter.count_tool_definition(tool)
    assert tok_tool > 0

    tok_list = counter.count_tool_definitions([tool, tool])
    assert tok_list == tok_tool * 2


# --- Seam 3: TiktokenCounter ---


def test_tiktoken_counter_raw_text():
    """Verify TiktokenCounter computes exact token counts for known strings."""
    counter = TiktokenCounter(model="gpt-4")

    assert counter.count_text("") == 0
    assert counter.count_text(None) == 0

    # "Hello, world!" is 4 tokens in cl100k_base
    count = counter.count_text("Hello, world!")
    assert count == 4


def test_tiktoken_counter_special_tokens_handling():
    """Verify TiktokenCounter does not crash on special tokens like <|endoftext|>."""
    counter = TiktokenCounter(model="gpt-4")
    raw = "Here is special: <|endoftext|> and <|im_start|>"
    # Should not raise ValueError
    tokens = counter.count_text(raw)
    assert tokens > 0


def test_tiktoken_counter_model_selection():
    """Verify TiktokenCounter selects appropriate encoding for gpt-4o vs gpt-4 vs grok."""
    c_4o = TiktokenCounter(model="gpt-4o")
    assert c_4o.encoding_name == "o200k_base"

    c_grok = TiktokenCounter(model="grok-2")
    assert c_grok.encoding_name == "cl100k_base"

    c_unknown = TiktokenCounter(model="unknown-future-model")
    assert c_unknown.encoding_name in ("cl100k_base", "o200k_base")


def test_tiktoken_counter_prompt_messages():
    """Verify TiktokenCounter calculates deterministic message tokens with overhead."""
    counter = TiktokenCounter(model="gpt-4")

    user_msg = PromptMessage(role=MessageRole.USER, content="Hello there")
    tok_user = counter.count_message(user_msg)
    assert tok_user > counter.count_text("Hello there")

    asst_msg = PromptMessage(
        role=MessageRole.ASSISTANT,
        content="Reading file",
        tool_calls=[ToolCall(id="call_99", name="read_file", arguments={"path": "foo.txt"})],
    )
    tok_asst = counter.count_message(asst_msg)
    assert tok_asst > counter.count_text("Reading file")

    msgs = [user_msg, asst_msg]
    assert counter.count_messages(msgs) == tok_user + tok_asst + 3


def test_tiktoken_counter_tool_definition():
    """Verify TiktokenCounter accurately estimates tool definitions."""
    counter = TiktokenCounter(model="gpt-4")

    tool = ToolDefinition(
        name="read_file",
        description="Read file contents from workspace",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    )
    tok = counter.count_tool_definition(tool)
    assert tok > 10


# --- Seam 4: Factory and Graceful Fallback ---


def test_get_token_counter_default_and_force_heuristic():
    """Verify get_token_counter returns TiktokenCounter by default and Heuristic when forced."""
    default_counter = get_token_counter(model="gpt-4")
    assert isinstance(default_counter, TiktokenCounter)
    assert isinstance(default_counter, TokenCounter)

    heuristic = get_token_counter(force_heuristic=True)
    assert isinstance(heuristic, HeuristicTokenCounter)
    assert isinstance(heuristic, TokenCounter)


def test_get_token_counter_graceful_fallback_on_import_error():
    """Verify get_token_counter falls back to HeuristicTokenCounter if tiktoken is missing."""
    with patch("icarus_core.tokens.counter.tiktoken", None):
        counter = get_token_counter(model="gpt-4")
        assert isinstance(counter, HeuristicTokenCounter)


# --- Seam 5: High-Level count_tokens Utility ---


def test_count_tokens_multi_type_dispatch():
    """Verify count_tokens works with raw text, PromptMessage, MessageDTO, and tools."""
    # Raw string
    assert count_tokens("Hello world") > 0
    assert count_tokens("") == 0
    assert count_tokens(None) == 0

    # PromptMessage
    pm = PromptMessage(role=MessageRole.USER, content="Hello")
    assert count_tokens(pm) > 0

    # MessageDTO
    from datetime import UTC, datetime

    dto = MessageDTO(
        id="m1",
        session_id="s1",
        role=MessageRole.USER,
        content="Hello DTO",
        created_at=datetime.now(UTC),
    )
    assert count_tokens(dto) > 0

    # MessageCreate
    mc = MessageCreate(session_id="s1", role=MessageRole.USER, content="Hello Create")
    assert count_tokens(mc) > 0

    # ToolDefinition
    tool = ToolDefinition(name="test_tool", description="A test", parameters={})
    assert count_tokens(tool) > 0

    # List of messages
    assert count_tokens([pm, dto]) > count_tokens(pm) + count_tokens(dto)
