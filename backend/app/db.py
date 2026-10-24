"""Database engine, session factory and shared column types.

The same models run on SQLite (local development without a server) and PostgreSQL.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """Stores UTC datetimes; always returns timezone-aware UTC values.

    SQLite has no timezone support, so values are stored as naive UTC and re-tagged on load.
    Naive datetimes are rejected on write so local times can't slip in unnoticed.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime passed to UTCDateTime column")
        value = value.astimezone(timezone.utc)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite":
        if url.database and url.database != ":memory:":
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(database_url, connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record) -> None:
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

        return engine
    return create_engine(database_url, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_session_factory() -> sessionmaker[Session]:
    global _engine, _session_factory
    if _session_factory is None:
        from app.core.config import get_settings

        _engine = make_engine(get_settings().database_url)
        _session_factory = make_session_factory(_engine)
    return _session_factory


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
