"""Fixtures for the UC-03 test suite.

Every test runs against a small scratch database built with the substrate
schema (two contacts, one company, notes, one order with a review and the
full-text index), never against ``substrate.db``. Masking tests use a stub
detector so no NER model loads; the stdio tests spawn the real server with
the committed manifest pin and strict verification on.
"""

from __future__ import annotations

import asyncio
import random
from datetime import date, datetime
from pathlib import Path

import pytest

from ucs.uc03_mcp_privacy.envelope import SessionEnvelope

# Values planted in the scratch database; masking tests assert none of them leaks.
JAN = {
    "first_name": "Jan",
    "last_name": "Novák",
    "email": "jan.novak@example.cz",
    "phone": "+420 601 111 222",
    "full_street": "Husova 14",
    "city": "Brno",
    "postal_code": "602 00",
    "iban": "CZ6508000000192000145399",
    "date_of_birth": date(1980, 5, 4),
}
EVA = {
    "first_name": "Eva",
    "last_name": "Nováková",
    "email": "eva.novakova@example.cz",
    "phone": "+420 602 333 444",
    "city": "Praha",
}
COMPANY = {"name": "Chocolate Cake s.r.o.", "ico": "12345678", "city": "Brno"}
NOTE_TEXTS = ("Volal kvůli reklamaci sluchátek.", "Domluvená schůzka na pondělí.")
REVIEW_CS = "Skvělá sluchátka, doporučuji každému."
# Every value the profiles promise to mask, every address part included.
PLANTED_VALUES = (
    JAN["first_name"],
    JAN["last_name"],
    JAN["email"],
    JAN["phone"],
    JAN["full_street"],
    JAN["city"],
    EVA["city"],
    JAN["postal_code"],
    JAN["iban"],
    JAN["date_of_birth"].isoformat(),
    EVA["first_name"],
    EVA["last_name"],
    EVA["email"],
    EVA["phone"],
    COMPANY["name"],
    COMPANY["ico"],
)


def stub_detector(text: str) -> list[dict]:
    """Deterministic stand-in for UC-02's rules + NER: finds the planted names and identifiers."""
    spans = []
    targets = (
        ("Jan Novák", "PERSON"),
        ("Novák", "PERSON"),
        ("Eva Nováková", "PERSON"),
        ("Emily", "PERSON"),
        ("Chocolate Cake", "ORG"),
        ("jan.novak@example.cz", "EMAIL"),
        ("+420 601 111 222", "PHONE"),
        ("605 123 456", "PHONE"),
    )
    taken: set[int] = set()
    for needle, pii_type in targets:
        start = text.find(needle)
        while start >= 0:
            end = start + len(needle)
            if not (set(range(start, end)) & taken):
                spans.append(
                    {
                        "span_start": start,
                        "span_end": end,
                        "pii_type": pii_type,
                        "surface_form": needle,
                        "source": "stub",
                    }
                )
                taken.update(range(start, end))
            start = text.find(needle, end)
    return sorted(spans, key=lambda s: s["span_start"])


def build_scratch_db(path: Path) -> Path:
    """Create a substrate-schema SQLite file with the planted rows and the reviews FTS index."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    from sqlmodel import SQLModel

    from substrate.pipeline.build_substrate_db import _FTS_CREATE, _FTS_REBUILD
    from substrate.schema.models import Company, Contact, Note, Order, Product, Review

    async def _write() -> None:
        """Create the schema, insert the planted rows, then build the reviews FTS index."""
        engine = create_async_engine(f"sqlite+aiosqlite:///{path}", future=True)
        factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        async with factory() as session:
            session.add(Company(**COMPANY))
            session.add(
                Product(name="Headphones X", name_cs="Sluchátka X", category="Audio", price=990.0)
            )
            await session.commit()
            session.add_all(
                [
                    Contact(
                        **JAN,
                        gender="m",
                        formal=True,
                        name_vocative="Vážený pane Nováku",
                        reviewer_id="R-A",
                        amazon_group="A",
                        is_clean=True,
                        company_id=1,
                        lifecycle_stage="active",
                        prior_interactions="Minule volal Jan Novák kvůli reklamaci.",
                    ),
                    Contact(
                        **EVA,
                        gender="f",
                        formal=True,
                        name_vocative="Vážená paní Nováková",
                        reviewer_id="R-B",
                        amazon_group="B",
                        is_clean=True,
                        lifecycle_stage="prospect",
                    ),
                ]
            )
            await session.commit()
            session.add_all(
                [
                    Note(
                        contact_id=1,
                        content=text,
                        category="general",
                        created_at=datetime(2014, 7, 1, 10, 0, i),
                    )
                    for i, text in enumerate(NOTE_TEXTS)
                ]
            )
            session.add(
                Order(
                    contact_id=1,
                    product_id=1,
                    quantity=1,
                    unit_price=990.0,
                    order_date=date(2014, 6, 1),
                )
            )
            await session.commit()
            session.add(
                Review(
                    contact_id=1,
                    order_id=1,
                    product_id=1,
                    rating=5.0,
                    review_date=date(2014, 6, 3),
                    summary_en="Great",
                    text_en="Great headphones, I recommend them.",
                    summary_cs="Skvělé",
                    text_cs=REVIEW_CS,
                )
            )
            await session.commit()
        async with engine.begin() as conn:
            await conn.exec_driver_sql(_FTS_CREATE)
            await conn.exec_driver_sql(_FTS_REBUILD)
        await engine.dispose()

    asyncio.run(_write())
    return path


@pytest.fixture(autouse=True)
def _model_calls_off(monkeypatch):
    """No test may reach a model: the global switch is forced off for the process."""
    monkeypatch.setenv("THESIS_LLM_CALLS", "FALSE")


@pytest.fixture
def scratch_db(tmp_path: Path) -> Path:
    """A fresh scratch database (see ``build_scratch_db``) under the test's temp directory."""
    return build_scratch_db(tmp_path / "uc03-scratch.db")


@pytest.fixture
def envelope(tmp_path: Path) -> SessionEnvelope:
    """A ``SessionEnvelope`` over a fresh session map, using the deterministic stub detector."""
    return SessionEnvelope(
        tmp_path / "session-map.json", detector=stub_detector, rng=random.Random(7)
    )
