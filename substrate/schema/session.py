"""
Async SQLite session factory for the shared substrate database.

The database path is ``utils.paths.SUBSTRATE_DB`` (substrate/snapshots/substrate.db,
gitignored) and nothing else. Every reader of the substrate -- this ORM layer and
the modules that open the file with ``sqlite3`` directly (UC-03 tools, the
frontend bridge, the audit gate) -- resolves it from that one constant, so no
switch can point them at different databases. Tests build their own in-memory
engine in ``tests/conftest.py``.

Session usage:
  get_session() is an async context manager, a thin wrapper over
  async_session_factory (which is equally fine to use directly):

    async with get_session() as session:
        session.add(obj)
        await session.commit()
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

# Import all models to register them with SQLModel.metadata
from substrate.schema.models import (  # noqa: F401
    Aspect,
    Company,
    Contact,
    LifecycleStage,
    MessageBrief,
    Note,
    Order,
    Product,
    Recommendation,
    Review,
    Topic,
)

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

from utils.paths import SUBSTRATE_DB

_DATABASE_URL: str = f"sqlite+aiosqlite:///{SUBSTRATE_DB}"

# ---------------------------------------------------------------------------
# Engine + session factory
# ---------------------------------------------------------------------------

engine = create_async_engine(
    _DATABASE_URL,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False},
)

async_session_factory = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """
    Create all tables defined in SQLModel.metadata.
    Safe to call multiple times (CREATE IF NOT EXISTS semantics).
    UC-01's demo CLI calls it at startup; the build chain and the test
    fixtures create the schema themselves.
    """
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield an AsyncSession as an ``async with`` context manager.

    Example:
        async with get_session() as session:
            session.add(contact)
            await session.commit()

    Smoke-test (inline):
        >>> import asyncio
        >>> from substrate.schema.session import get_session
        >>> async def _probe():
        ...     async with get_session() as session:
        ...         return session is not None
        >>> asyncio.run(_probe())
        True
    """
    async with async_session_factory() as session:
        yield session
