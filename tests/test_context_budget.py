"""Unit and integration tests for Context Budget Manager and Context Hierarchy Assembly."""

from pathlib import Path
from unittest.mock import MagicMock

from icarus_contracts import (
    ContextBudgetConfig,
    ContextBudgetStatus,
    IcarusConfig,
    MessageRole,
    PromptMessage,
    ProviderCapabilities,
    ToolDefinition,
)
from icarus_core.agent.context import ContextBudgetManager
from icarus_core.config import ConfigManager
from icarus_core.tokens import HeuristicTokenCounter

# --- Seam 1: ContextBudgetConfig calculations ---


def test_context_budget_config_defaults():
    """Verify default values and calculation properties of ContextBudgetConfig."""
    cfg = ContextBudgetConfig()
    assert cfg.context_window == 128000
    assert cfg.output_reserve == 4000
    assert cfg.safety_margin == 2000
    assert cfg.compaction_threshold == 0.8

    # input_budget = 128000 - 4000 - 2000 = 122000
    assert cfg.input_budget == 122000
    # compaction_trigger_tokens = int(122000 * 0.8) = 97600
    assert cfg.compaction_trigger_tokens == 97600


def test_context_budget_config_custom_and_clamping():
    """Verify custom values and edge-case clamping when reserves exceed window."""
    cfg = ContextBudgetConfig(
        context_window=8000,
        output_reserve=1500,
        safety_margin=500,
        compaction_threshold=0.75,
    )
    assert cfg.input_budget == 6000
    assert cfg.compaction_trigger_tokens == 4500

    # Over-reserved window clamps input_budget to 0
    small_cfg = ContextBudgetConfig(
        context_window=1000,
        output_reserve=800,
        safety_margin=400,
    )
    assert small_cfg.input_budget == 0
    assert small_cfg.compaction_trigger_tokens == 0


# --- Seam 2: IcarusConfig and ConfigManager integration ---


def test_icarus_config_budget_fields():
    """Verify IcarusConfig contains new context budget fields with correct defaults."""
    cfg = IcarusConfig()
    assert cfg.safety_margin_tokens == 2000
    assert cfg.output_reserve_tokens == 4000
    assert cfg.compaction_threshold == 0.8


def test_config_manager_persists_context_budget_fields(tmp_path: Path):
    """Verify ConfigManager correctly writes and reads context budget fields from config.toml."""
    config_file = tmp_path / "config.toml"
    mgr = ConfigManager(config_path=config_file)

    initial = mgr.load_config()
    assert initial.safety_margin_tokens == 2000
    assert initial.output_reserve_tokens == 4000
    assert initial.compaction_threshold == 0.8

    mgr.set("safety_margin_tokens", 3000)
    mgr.set("output_reserve_tokens", 5000)
    mgr.set("compaction_threshold", 0.85)

    reloaded = mgr.load_config()
    assert reloaded.safety_margin_tokens == 3000
    assert reloaded.output_reserve_tokens == 5000
    assert reloaded.compaction_threshold == 0.85


# --- Seam 3: ContextBudgetManager budget calculations & provider adaptation ---


def test_budget_manager_input_budget_calculation():
    """Verify ContextBudgetManager computes dynamic input budget correctly."""
    cfg = ContextBudgetConfig(
        context_window=16000,
        output_reserve=2000,
        safety_margin=1000,
        compaction_threshold=0.8,
    )
    mgr = ContextBudgetManager(config=cfg)
    assert mgr.calculate_input_budget() == 13000

    # Override context window dynamically
    assert mgr.calculate_input_budget(context_window=32000) == 29000


def test_budget_manager_from_provider_capabilities():
    """Verify ContextBudgetManager adapts to provider capabilities."""
    mock_provider = MagicMock()
    mock_provider.get_capabilities.return_value = ProviderCapabilities(
        max_context_tokens=64000,
    )
    mgr = ContextBudgetManager.from_provider(
        provider=mock_provider,
        model="custom-model",
        output_reserve=3000,
        safety_margin=1000,
    )
    assert mgr.config.context_window == 64000
    assert mgr.calculate_input_budget() == 60000


# --- Seam 4: Compaction threshold detection & status reporting ---


def test_budget_manager_threshold_detection():
    """Verify compaction trigger detection under and over threshold."""
    # Use deterministic heuristic counter
    counter = HeuristicTokenCounter(chars_per_token=4.0)
    cfg = ContextBudgetConfig(
        context_window=1000,
        output_reserve=200,
        safety_margin=100,
        compaction_threshold=0.5,
    )
    # input_budget = 700 tokens, trigger = 350 tokens
    mgr = ContextBudgetManager(config=cfg, token_counter=counter)

    # Short message: ~20 chars -> ~5 tokens + 4 overhead = 9 tokens
    msgs_short = [PromptMessage(role=MessageRole.USER, content="Short user message")]
    assert not mgr.is_compaction_needed(msgs_short)

    # Long message: 1600 chars -> ~400 tokens -> exceeds 350 trigger
    msgs_long = [PromptMessage(role=MessageRole.USER, content="A" * 1600)]
    assert mgr.is_compaction_needed(msgs_long)


def test_budget_manager_status_snapshot():
    """Verify get_budget_status returns a complete, accurate ContextBudgetStatus."""
    counter = HeuristicTokenCounter(chars_per_token=4.0)
    cfg = ContextBudgetConfig(
        context_window=2000,
        output_reserve=400,
        safety_margin=200,
        compaction_threshold=0.8,
    )
    # input_budget = 1400 tokens, trigger = 1120 tokens
    mgr = ContextBudgetManager(config=cfg, token_counter=counter)

    msgs = [
        PromptMessage(role=MessageRole.SYSTEM, content="System prompt instructions"),
        PromptMessage(role=MessageRole.USER, content="User question"),
    ]
    status = mgr.get_budget_status(messages=msgs)

    assert isinstance(status, ContextBudgetStatus)
    assert status.context_window == 2000
    assert status.input_budget == 1400
    assert status.compaction_threshold_tokens == 1120
    assert status.total_estimated_tokens > 0
    assert status.remaining_budget == 1400 - status.total_estimated_tokens
    assert 0.0 <= status.utilization_ratio <= 1.0
    assert not status.compaction_needed


def test_budget_manager_accounts_for_tools_in_status():
    """Verify status accounts for tools schemas in budget allocation."""
    counter = HeuristicTokenCounter()
    cfg = ContextBudgetConfig(context_window=2000, output_reserve=400, safety_margin=200)
    mgr = ContextBudgetManager(config=cfg, token_counter=counter)

    tool = ToolDefinition(
        name="read_file",
        description="Read file contents from filesystem",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    )

    status_no_tools = mgr.get_budget_status(messages=[])
    status_with_tools = mgr.get_budget_status(messages=[], tools=[tool])

    assert status_with_tools.tools_tokens > 0
    assert status_with_tools.total_estimated_tokens > status_no_tools.total_estimated_tokens


# --- Seam 5: Context Hierarchy Assembly ---


def test_context_hierarchy_assembly_order():
    """Verify assemble_prompt strictly orders context elements:
    1. System persona & safety instructions
    2. Task constraints / instructions
    3. Compaction summary (if present)
    4. Recent conversation turns
    """
    mgr = ContextBudgetManager()

    system_persona = "You are Icarus. Follow safety guidelines."
    task_constraints = "Do not modify files in /etc."
    compaction_summary = "User previously explored the codebase and tested utils."
    history = [
        PromptMessage(role=MessageRole.USER, content="What is the next step?"),
        PromptMessage(role=MessageRole.ASSISTANT, content="We need to run tests."),
    ]

    assembled = mgr.assemble_prompt(
        system_prompt=system_persona,
        task_constraints=task_constraints,
        compaction_summary=compaction_summary,
        history_messages=history,
    )

    assert len(assembled) == 5

    # 1. System Persona & Safety
    assert assembled[0].role == MessageRole.SYSTEM
    assert "You are Icarus" in (assembled[0].content or "")

    # 2. Task constraints
    assert assembled[1].role == MessageRole.SYSTEM
    assert "Do not modify files in /etc" in (assembled[1].content or "")
    assert "[Task Constraints]" in (assembled[1].content or "")

    # 3. Compaction summary
    assert assembled[2].role == MessageRole.SYSTEM
    assert "User previously explored" in (assembled[2].content or "")
    assert "[Previous Conversation Summary]" in (assembled[2].content or "")

    # 4. Recent history
    assert assembled[3].role == MessageRole.USER
    assert assembled[3].content == "What is the next step?"


def test_context_hierarchy_assembly_without_optional_elements():
    """Verify assemble_prompt works cleanly when task constraints or summary are absent."""
    mgr = ContextBudgetManager()

    history = [
        PromptMessage(role=MessageRole.USER, content="Hello"),
    ]

    assembled = mgr.assemble_prompt(
        system_prompt="Base system prompt",
        history_messages=history,
    )

    assert len(assembled) == 2
    assert assembled[0].role == MessageRole.SYSTEM
    assert assembled[0].content == "Base system prompt"
    assert assembled[1].role == MessageRole.USER
    assert assembled[1].content == "Hello"


def test_context_hierarchy_preserves_existing_system_prompt_if_not_provided():
    """Verify assemble_prompt preserves leading system message when no explicit prompt given."""
    mgr = ContextBudgetManager()

    history = [
        PromptMessage(role=MessageRole.SYSTEM, content="Existing system"),
        PromptMessage(role=MessageRole.USER, content="User message"),
    ]

    assembled = mgr.assemble_prompt(
        system_prompt=None,
        history_messages=history,
    )

    assert len(assembled) == 2
    assert assembled[0].role == MessageRole.SYSTEM
    assert assembled[0].content == "Existing system"
    assert assembled[1].role == MessageRole.USER
    assert assembled[1].content == "User message"
