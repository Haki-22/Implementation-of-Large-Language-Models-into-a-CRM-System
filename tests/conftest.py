"""
Pytest fixtures for the thesis test suite (all UCs).

Provides:
  - Async in-memory SQLite session (per-test isolation)
  - Synthetic Contact and MessageBrief factories
  - Mock LLM provider for cost-free unit tests

Usage:
    async def test_something(async_session, contact_factory, brief_factory):
        contact = contact_factory(gender="m", formal=True)
        ...

Mock provider:
    The mock_provider fixture returns an async callable that returns a fixed
    Czech message string without hitting any real LLM API.  Tests that need
    a specific response can override via mock_provider.return_value.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncGenerator
from typing import Any, Callable
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from utils.paths import THESIS_ROOT as PROJECT_ROOT

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import all DB models to register them with SQLModel.metadata
from substrate.schema.models import (  # noqa: E402, F401
    Company,
    Contact,
    MessageBrief,
    Note,
    Order,
    Product,
    Review,
)


# ---------------------------------------------------------------------------
# Event loop (session-scoped)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def event_loop():
    """Session-scoped event loop for pytest-asyncio."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Async in-memory SQLite session (per test)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield a fresh async in-memory SQLite session for each test.

    All DB tables are created on entry and the engine is disposed
    on exit.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
        connect_args={"check_same_thread": False},
    )

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    await engine.dispose()


# ---------------------------------------------------------------------------
# Contact factory
# ---------------------------------------------------------------------------


@pytest.fixture
def contact_factory() -> Callable[..., Contact]:
    """
    Return a factory function that creates unsaved Contact instances.

    Defaults produce a clean formal-male Czech contact ready for UC-01
    generation.  Override any field by keyword argument.

    Example:
        clean_male = contact_factory()
        non_clean  = contact_factory(gender=None, is_clean=False)
        informal_f = contact_factory(gender="f", formal=False,
                                     name_vocative="Ahoj Jano")
    """

    def _factory(
        first_name: str = "Jan",
        last_name: str = "Novák",
        nickname: str | None = None,
        gender: str | None = "m",
        formal: bool | None = True,
        name_vocative: str | None = "Vážený pane Nováku",
        company_id: int | None = None,
        title: str | None = None,
        ocean: dict[str, float] | None = None,
        frequent_words: list[str] | None = None,
        prior_interactions: str | None = None,
        is_clean: bool = True,
        **kwargs: Any,
    ) -> Contact:
        """Build one unsaved ``Contact`` with clean formal-male defaults, overridable by keyword."""
        fw_json = (
            json.dumps(frequent_words, ensure_ascii=False) if frequent_words is not None else None
        )
        return Contact(
            first_name=first_name,
            last_name=last_name,
            nickname=nickname,
            gender=gender,
            formal=formal,
            name_vocative=name_vocative,
            company_id=company_id,
            title=title,
            ocean=ocean,
            frequent_words=fw_json,
            prior_interactions=prior_interactions,
            is_clean=is_clean,
            **kwargs,
        )

    return _factory


# ---------------------------------------------------------------------------
# MessageBrief factory
# ---------------------------------------------------------------------------


@pytest.fixture
def brief_factory() -> Callable[..., MessageBrief]:
    """
    Return a factory function that creates unsaved MessageBrief instances.

    Defaults produce a short invitation brief.  Override any field by
    keyword argument.

    Example:
        brief = brief_factory()
        upsell = brief_factory(title="upsell_offer",
                               default_template="Nabízíme upgrade na prémiové členství.",
                               category="upsell")
    """

    def _factory(
        title: str = "seasonal_sale_invitation",
        default_template: str = (
            "Pozvánka na jarní výprodej — slevy až 40 % na vybrané zboží, jen do konce dubna."
        ),
        category: str | None = "invitation",
        **kwargs: Any,
    ) -> MessageBrief:
        """Build one unsaved ``MessageBrief`` with invitation defaults, overridable by keyword."""
        return MessageBrief(
            title=title,
            default_template=default_template,
            category=category,
            **kwargs,
        )

    return _factory


# ---------------------------------------------------------------------------
# Mock LLM provider
# ---------------------------------------------------------------------------


_MOCK_RESPONSE = (
    "Vážený pane Nováku,\n\n"
    "dovolujeme si Vám oznámit, že Vaše objednávka č. 20261234 byla odeslána "
    "a dorazí do 3 pracovních dnů. "
    "Těšíme se na Vaši další návštěvu.\n\n"
    "S pozdravem,\nZákaznický servis"
)


@pytest.fixture
def mock_provider() -> AsyncMock:
    """
    Async mock for the LLM generation call used by UC-01 generators.

    Returns a fixed valid Czech message by default.  Tests that require
    a specific response can set mock_provider.return_value or configure
    mock_provider.side_effect.

    Usage:
        async def test_something(mock_provider, monkeypatch):
            monkeypatch.setattr(
                "utils.generation.generate_text",
                mock_provider,
            )
            ...
    """
    mock = AsyncMock(return_value=_MOCK_RESPONSE)
    return mock


# ---------------------------------------------------------------------------
# Convenience fixtures: pre-saved clean contacts + brief
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def clean_male_contact(
    async_session: AsyncSession,
    contact_factory: Callable[..., Contact],
) -> Contact:
    """A saved clean formal-male contact."""
    contact = contact_factory()
    async_session.add(contact)
    await async_session.commit()
    await async_session.refresh(contact)
    return contact


@pytest_asyncio.fixture
async def clean_female_contact(
    async_session: AsyncSession,
    contact_factory: Callable[..., Contact],
) -> Contact:
    """A saved clean formal-female contact."""
    contact = contact_factory(
        first_name="Jana",
        last_name="Nováková",
        gender="f",
        formal=True,
        name_vocative="Vážená paní Nováková",
    )
    async_session.add(contact)
    await async_session.commit()
    await async_session.refresh(contact)
    return contact


@pytest_asyncio.fixture
async def clean_informal_male(
    async_session: AsyncSession,
    contact_factory: Callable[..., Contact],
) -> Contact:
    """A saved clean informal-male contact."""
    contact = contact_factory(
        first_name="Honza",
        last_name="Novotný",
        gender="m",
        formal=False,
        name_vocative="Ahoj Honzo",
    )
    async_session.add(contact)
    await async_session.commit()
    await async_session.refresh(contact)
    return contact


@pytest_asyncio.fixture
async def sample_brief(
    async_session: AsyncSession,
    brief_factory: Callable[..., MessageBrief],
) -> MessageBrief:
    """A saved invitation brief."""
    brief = brief_factory()
    async_session.add(brief)
    await async_session.commit()
    await async_session.refresh(brief)
    return brief
