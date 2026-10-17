"""Filesystem path helpers and resolution for Icarus Agent state."""

import os
from pathlib import Path

DEFAULT_ICARUS_DIR_NAME = ".icarus"


def get_icarus_home() -> Path:
    """Return the base directory for Icarus user state (~/.icarus or ICARUS_HOME)."""
    env_home = os.environ.get("ICARUS_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()
    return (Path.home() / DEFAULT_ICARUS_DIR_NAME).resolve()


def get_icarus_config_path() -> Path:
    """Return path to config.toml."""
    return get_icarus_home() / "config.toml"


def get_icarus_db_path() -> Path:
    """Return path to SQLite database."""
    return get_icarus_home() / "icarus.db"


def get_icarus_logs_dir() -> Path:
    """Return path to rotating logs directory (~/.icarus/logs or ICARUS_LOG_DIR)."""
    env_log_dir = os.environ.get("ICARUS_LOG_DIR") or os.environ.get("OPENAGENT_LOG_DIR")
    if env_log_dir:
        return Path(env_log_dir).expanduser().resolve()
    return get_icarus_home() / "logs"


def get_icarus_log_file() -> Path:
    """Return path to default cli.log file."""
    return get_icarus_logs_dir() / "cli.log"
