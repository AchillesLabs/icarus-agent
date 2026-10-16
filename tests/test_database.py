"""Tests for DatabaseManager connection lifecycle and session scoping."""

from pathlib import Path
from unittest.mock import patch

import pytest
from icarus_core.persistence.database import DatabaseManager
from sqlalchemy import text


def test_database_manager_default_path(tmp_path: Path):
    with patch("icarus_core.paths.get_icarus_home", return_value=tmp_path):
        manager = DatabaseManager()
        expected_path = tmp_path / "icarus.db"
        assert expected_path.as_posix() in manager.db_url
        assert manager.db_url.startswith("sqlite:///")


def test_database_manager_in_memory_override():
    manager = DatabaseManager(db_url="sqlite:///:memory:")
    assert manager.db_url == "sqlite:///:memory:"
    assert manager.is_connected() is True


def test_database_manager_executes_query():
    manager = DatabaseManager(db_url="sqlite:///:memory:")
    with manager.session_scope() as session:
        result = session.execute(text("SELECT 42")).scalar_one()
        assert result == 42


def test_database_manager_rollback_on_error():
    manager = DatabaseManager(db_url="sqlite:///:memory:")
    with manager.session_scope() as session:
        session.execute(text("CREATE TABLE test_items (id INT PRIMARY KEY, name TEXT)"))

    with pytest.raises(RuntimeError), manager.session_scope() as session:
        session.execute(text("INSERT INTO test_items VALUES (1, 'item1')"))
        raise RuntimeError("Forced abort")

    with manager.session_scope() as session:
        count = session.execute(text("SELECT count(*) FROM test_items")).scalar_one()
        assert count == 0


def test_database_manager_foreign_keys_enabled():
    manager = DatabaseManager(db_url="sqlite:///:memory:")
    with manager.session_scope() as session:
        fk_status = session.execute(text("PRAGMA foreign_keys")).scalar_one()
        assert fk_status == 1
