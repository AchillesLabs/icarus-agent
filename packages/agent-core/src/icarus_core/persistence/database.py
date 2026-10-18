"""Database connection and session lifecycle management for SQLAlchemy 2."""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool

from icarus_core.paths import get_icarus_db_path


class DatabaseManager:
    """Manages SQLite/PostgreSQL connection pool, engine configuration, and session scopes."""

    def __init__(
        self,
        db_url: str | None = None,
        *,
        pool_size: int = 10,
        max_overflow: int = 20,
        pool_pre_ping: bool = True,
        pool_recycle: int = 1800,
        pool_timeout: int = 30,
    ) -> None:
        if db_url is not None:
            self._db_url = db_url
        else:
            db_path = get_icarus_db_path()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db_url = f"sqlite:///{db_path.as_posix()}"

        self._pool_size = pool_size
        self._max_overflow = max_overflow
        self._pool_pre_ping = pool_pre_ping
        self._pool_recycle = pool_recycle
        self._pool_timeout = pool_timeout

        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    @property
    def db_url(self) -> str:
        """Return the active database connection URL."""
        return self._db_url

    @property
    def is_postgres(self) -> bool:
        """Return True if the configured database is PostgreSQL."""
        return self._db_url.startswith(("postgresql", "postgres"))

    @property
    def is_sqlite(self) -> bool:
        """Return True if the configured database is SQLite."""
        return self._db_url.startswith("sqlite")

    @property
    def engine(self) -> Engine:
        """Lazily initialize and return the SQLAlchemy Engine."""
        if self._engine is None:
            engine_kwargs: dict[str, Any] = {}
            effective_url = self._db_url

            if self.is_postgres:
                # Normalize deprecated postgres:// or bare postgresql:// to postgresql+psycopg://
                if effective_url.startswith("postgres://"):
                    effective_url = "postgresql+psycopg://" + effective_url[len("postgres://") :]
                elif effective_url.startswith("postgresql://"):
                    effective_url = "postgresql+psycopg://" + effective_url[len("postgresql://") :]

                engine_kwargs["poolclass"] = QueuePool
                engine_kwargs["pool_size"] = self._pool_size
                engine_kwargs["max_overflow"] = self._max_overflow
                engine_kwargs["pool_pre_ping"] = self._pool_pre_ping
                engine_kwargs["pool_recycle"] = self._pool_recycle
                engine_kwargs["pool_timeout"] = self._pool_timeout
            elif self.is_sqlite:
                engine_kwargs["connect_args"] = {"check_same_thread": False}
                if self._db_url == "sqlite:///:memory:" or ":memory:" in self._db_url:
                    engine_kwargs["poolclass"] = StaticPool

            self._engine = create_engine(effective_url, **engine_kwargs)

            # Configure SQLite pragmas on connect
            if self.is_sqlite:

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
