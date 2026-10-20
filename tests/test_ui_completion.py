"""Tests for IcarusSlashCompleter and interactive command autocomplete."""

from icarus_cli.ui.completion import IcarusSlashCompleter
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document


def test_autocomplete_triggers_on_slash():
    """Typing '/' at start of input presents registered slash commands."""
    completer = IcarusSlashCompleter()
    doc = Document("/", cursor_position=1)
    event = CompleteEvent()

    completions = list(completer.get_completions(doc, event))
    texts = [c.text for c in completions]
    display_texts = [getattr(c, "display_text", str(c.display)) for c in completions]

    assert "help" in texts
    assert "model" in texts
    assert "models" in texts
    assert "toolsets" in texts
    assert "integrations" in texts
    assert "tools" in texts
    assert "skills" in texts
    assert "theme" in texts
    assert "clear" in texts
    assert "exit" in texts
    assert any("/help" in d for d in display_texts)


def test_autocomplete_filters_by_prefix():
    """Typing a partial command filters matching options."""
    completer = IcarusSlashCompleter()

    # /mod -> /model, /models
    doc = Document("/mod", cursor_position=4)
    completions = list(completer.get_completions(doc, CompleteEvent()))
    texts = [c.text for c in completions]
    assert "model" in texts
    assert "models" in texts
    assert "help" not in texts

    # /the -> /theme
    doc_theme = Document("/the", cursor_position=4)
    completions_theme = list(completer.get_completions(doc_theme, CompleteEvent()))
    texts_theme = [c.text for c in completions_theme]
    assert "theme" in texts_theme
    assert "model" not in texts_theme


def test_autocomplete_subcommands():
    """Subcommands are suggested for commands with sub-actions."""
    completer = IcarusSlashCompleter()

    # /toolsets <space>
    doc = Document("/toolsets ", cursor_position=10)
    completions = list(completer.get_completions(doc, CompleteEvent()))
    texts = [c.text for c in completions]
    assert "list" in texts
    assert "enable" in texts
    assert "disable" in texts
    assert "reset" in texts

    # /integrations <space>
    doc_int = Document("/integrations ", cursor_position=14)
    completions_int = list(completer.get_completions(doc_int, CompleteEvent()))
    texts_int = [c.text for c in completions_int]
    assert "connect" in texts_int
    assert "status" in texts_int
    assert "disconnect" in texts_int
    assert "doctor" in texts_int


def test_autocomplete_ignores_normal_chat():
    """Normal user text, arithmetic, paths, and URLs do not trigger slash command completion."""
    completer = IcarusSlashCompleter()

    normal_inputs = [
        "What is the weather in Delhi?",
        "Look at path/to/file.py",
        "The answer is 1/2",
        "https://google.com/search",
        "git checkout branch/feature",
        "echo 4 / 2",
    ]

    for user_text in normal_inputs:
        doc = Document(user_text, cursor_position=len(user_text))
        completions = list(completer.get_completions(doc, CompleteEvent()))
        assert len(completions) == 0, f"Expected 0 completions for '{user_text}', got {completions}"
