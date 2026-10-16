"""Database connection and session lifecycle management for SQLAlchemy 2."""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from icarus_core.paths import get_icarus_db_path


class DatabaseManager:
    """Manages SQLite/database connection pool, engine configuration, and session scopes."""

    def __init__(self, db_url: str | None = None) -> None:
        if db_url is not None:
            self._db_url = db_url
        else:
            db_path = get_icarus_db_path()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db_url = f"sqlite:///{db_path.as_posix()}"

        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    @property
    def db_url(self) -> str:
        """Return the active database connection URL."""
        return self._db_url

    @property
    def engine(self) -> Engine:
        """Lazily initialize and return the SQLAlchemy Engine."""
        if self._engine is None:
            engine_kwargs: dict[str, Any] = {}
            if self._db_url.startswith("sqlite"):
                engine_kwargs["connect_args"] = {"check_same_thread": False}
                if self._db_url == "sqlite:///:memory:" or ":memory:" in self._db_url:
                    engine_kwargs["poolclass"] = StaticPool

            self._engine = create_engine(self._db_url, **engine_kwargs)

            # Configure SQLite pragmas on connect
            if self._db_url.startswith("sqlite"):

                @event.listens_for(self._engine, "connect")
                def _set_sqlite_pragmas(dbapi_connection: Any, connection_record: Any) -> None:
                    cursor = dbapi_connection.cursor()
                    cursor.execute("PRAGMA foreign_keys=ON")
                    if ":memory:" not in self._db_url:
                        cursor.execute("PRAGMA journal_mode=WAL")
                    cursor.close()

        return self._engine

    @property
    def session_factory(self) -> sessionmaker[Session]:
        """Return the configured sessionmaker."""
        if self._session_factory is None:
            self._session_factory = sessionmaker(
                bind=self.engine,
                expire_on_commit=False,
                autoflush=False,
                autocommit=False,
            )
        return self._session_factory

    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """Provide a transactional scope around a series of operations."""
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def is_connected(self) -> bool:
        """Verify database reachability and execute a connectivity probe."""
        try:
            with self.session_scope() as session:
                session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def close(self) -> None:
        """Dispose of the engine connection pool."""
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None
