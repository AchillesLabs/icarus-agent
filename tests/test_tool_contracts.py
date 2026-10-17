"""Tests for tool contracts and schemas."""

from icarus_contracts.session import MessageRole
from icarus_contracts.tools import (
    ToolCall,
    ToolDefinition,
    ToolResult,
    ToolSafetyCategory,
)


def test_tool_safety_category_values():
    """ToolSafetyCategory enum includes SAFE_READ and REQUIRES_APPROVAL."""
    assert ToolSafetyCategory.SAFE_READ.value == "safe_read"
    assert ToolSafetyCategory.REQUIRES_APPROVAL.value == "requires_approval"


def test_tool_definition_openai_schema_generation():
    """ToolDefinition renders an OpenAI-compatible function calling schema."""
    definition = ToolDefinition(
        name="read_file",
        description="Read file contents within workspace",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path"},
                "offset": {"type": "integer", "description": "Starting line number", "default": 1},
            },
            "required": ["path"],
        },
        safety_category=ToolSafetyCategory.SAFE_READ,
    )

    schema = definition.to_openai_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "read_file"
    assert schema["function"]["description"] == "Read file contents within workspace"
    assert "path" in schema["function"]["parameters"]["properties"]
    assert schema["function"]["parameters"]["required"] == ["path"]


def test_tool_call_supports_dict_and_json_arguments():
    """ToolCall normalizes dictionary and JSON string arguments."""
    call_with_dict = ToolCall(
        id="call_123",
        name="read_file",
        arguments={"path": "src/main.py", "offset": 5},
    )
    assert call_with_dict.id == "call_123"
    assert call_with_dict.name == "read_file"
    assert call_with_dict.arguments == {"path": "src/main.py", "offset": 5}

    call_with_json_str = ToolCall(
        id="call_456",
        name="list_dir",
        arguments='{"path": "tests"}',
    )
    assert call_with_json_str.get_arguments_dict() == {"path": "tests"}


def test_tool_result_to_prompt_message():
    """ToolResult converts to PromptMessage with role='tool'."""
    res_success = ToolResult(
        call_id="call_123",
        name="read_file",
        output="print('hello')",
        exit_code=0,
    )
    msg = res_success.to_prompt_message()
    assert msg.role in (MessageRole.TOOL, "tool")
    assert msg.name == "read_file"
    assert msg.content == "print('hello')"

    res_error = ToolResult(
        call_id="call_999",
        name="read_file",
        output="",
        error="File not found: missing.txt",
        exit_code=1,
    )
    err_msg = res_error.to_prompt_message()
    assert err_msg.role in (MessageRole.TOOL, "tool")
    assert "File not found" in err_msg.content
