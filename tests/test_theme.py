"""Tests for UITheme customization and color management."""

from pathlib import Path

import pytest
from icarus_core.theme import get_theme, list_themes, set_theme


def test_get_theme_default():
    """Default theme is purple with correct color tokens."""
    theme = get_theme("purple")
    assert theme.name == "purple"
    assert theme.primary == "#C084FC"
    assert theme.border == "#A855F7"
    assert theme.secondary == "#E9D5FF"
    assert theme.prompt_ansi == "ansimagenta"


def test_get_theme_presets():
    """All preset themes are resolvable with valid hex color tokens."""
    for name in ("purple", "cyan", "green", "amber", "red", "blue", "pink"):
        theme = get_theme(name)
        assert theme.name == name
        assert theme.primary.startswith("#")
        assert theme.border.startswith("#")
        assert theme.secondary.startswith("#")


def test_get_theme_custom_hex():
    """Custom hex codes create a valid custom UITheme."""
    theme = get_theme("#FF5500")
    assert theme.name == "#ff5500"
    assert theme.primary == "#FF5500"
    assert theme.border == "#FF5500"

    # Hex without leading hash is also accepted
    theme2 = get_theme("00AACC")
    assert theme2.name == "#00aacc"
    assert theme2.primary == "#00AACC"


def test_custom_hex_validation_error():
    """Invalid hex strings raise ValueError."""
    with pytest.raises(ValueError):
        get_theme("not-a-color-and-not-a-hex")


def test_list_themes_contains_all_presets():
    """list_themes returns all preset palettes."""
    themes = list_themes()
    assert "purple" in themes
    assert "cyan" in themes
    assert "green" in themes
    assert "amber" in themes
    assert "red" in themes
    assert "blue" in themes
    assert "pink" in themes


def test_set_theme_persists_and_resets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """set_theme persists the chosen theme into ~/.icarus/config.toml."""
    fake_config = tmp_path / "config.toml"
    from icarus_core import paths

    monkeypatch.setattr(paths, "get_icarus_config_path", lambda: fake_config)

    # Set to cyan
    new_theme = set_theme("cyan")
    assert new_theme.name == "cyan"

    # Read back
    active = get_theme()
    assert active.name == "cyan"
    assert active.primary == "#38BDF8"

    # Reset back to purple
    set_theme("purple")
    assert get_theme().name == "purple"
