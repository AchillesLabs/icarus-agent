"""Global pytest fixtures and configuration."""

import os

import pytest

# Neutralize terminal color and ANSI styling before CLI modules/rich are imported
os.environ["NO_COLOR"] = "1"
os.environ["TERM"] = "dumb"
os.environ.pop("FORCE_COLOR", None)


@pytest.fixture(autouse=True, scope="session")
def disable_terminal_color_for_tests():
    """Ensure consistent, predictable CLI output across CI and local environments."""
    os.environ["NO_COLOR"] = "1"
    os.environ["TERM"] = "dumb"
    os.environ.pop("FORCE_COLOR", None)
