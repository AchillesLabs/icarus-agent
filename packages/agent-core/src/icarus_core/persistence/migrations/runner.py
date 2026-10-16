"""Alembic migration runner for automatic schema upgrades and revision checks."""

from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from icarus_core.persistence.database import DatabaseManager


class MigrationRunner:
    """Orchestrates automatic Alembic migrations and database schema revision verification."""

    def __init__(self, migrations_dir: Path | None = None) -> None:
        self.migrations_dir = (
            migrations_dir if migrations_dir is not None else Path(__file__).parent
        )

    def get_alembic_config(
        self,
        db_url: str | None = None,
        connection: Any = None,
    ) -> Config:
        """Create and populate an Alembic Config instance."""
        config = Config()
        config.set_main_option("script_location", self.migrations_dir.as_posix())
        if db_url is not None:
            config.set_main_option("sqlalchemy.url", db_url)
        if connection is not None:
            config.attributes["connection"] = connection
        return config

    def get_head_revision(self) -> str:
        """Return the latest migration revision identifier defined in versions/."""
        config = self.get_alembic_config()
        script = ScriptDirectory.from_config(config)
        head = script.get_current_head()
        if head is None:
            raise RuntimeError("No Alembic revisions found in migrations directory.")
        return head

    def get_current_revision(
        self,
        db_url: str | None = None,
        db_manager: DatabaseManager | None = None,
    ) -> str | None:
        """Inspect the active database and return the current applied migration revision."""
        manager = db_manager or DatabaseManager(db_url=db_url)
        try:
            with manager.engine.connect() as connection:
                context = MigrationContext.configure(connection)
                return context.get_current_revision()
        except Exception:
            return None

    def is_migration_up_to_date(
        self,
        db_url: str | None = None,
        db_manager: DatabaseManager | None = None,
    ) -> bool:
        """Return True if the database schema is up-to-date with the head revision."""
        current = self.get_current_revision(db_url=db_url, db_manager=db_manager)
        if current is None:
            return False
        return current == self.get_head_revision()

    def run_migrations(
        self,
        db_url: str | None = None,
        db_manager: DatabaseManager | None = None,
        target_revision: str = "head",
    ) -> None:
        """Execute pending Alembic migrations up to the target revision (defaults to head)."""
        manager = db_manager or DatabaseManager(db_url=db_url)
        with manager.engine.connect() as connection:
            config = self.get_alembic_config(db_url=manager.db_url, connection=connection)
            command.upgrade(config, target_revision)
            connection.commit()
