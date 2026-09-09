"""
Schema regression tests for the shared thesis CRM substrate.

Covers:
- Contact PII fields (email, phone, full_street, city,
  postal_code, date_of_birth, bank_account, iban)
- Company registry fields (ico, dic, full_street, city, postal_code,
  legal_form)
- Product extended columns (category, price, description, sku)
- New Order table with FK constraints

All assertions are structural (constructor + attribute access) — no DB
round-trip write is required for these checks.  The engine.begin() block
verifies that SQLModel.metadata.create_all() succeeds without DDL errors.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel


@pytest.mark.asyncio
async def test_new_schema_fields_and_tables():
    from substrate.schema.models import Contact, Company, Product, Order, Note

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await engine.dispose()

    c = Contact(
        first_name="Jan",
        last_name="Novak",
        email="j@x.cz",
        phone="+420 601 000 000",
        full_street="Krátká 1",
        city="Brno",
        postal_code="602 00",
        bank_account="1/0100",
        iban="CZ6501000000000000000001",
        reviewer_id="A123",
        amazon_group="B",
    )
    assert c.email and c.full_street and c.iban
    assert c.reviewer_id == "A123" and c.amazon_group == "B"

    co = Company(
        name="ACME s.r.o.",
        ico="25596641",
        dic="CZ25596641",
        full_street="Dlouhá 5",
        city="Praha",
        postal_code="110 00",
        legal_form="s.r.o.",
    )
    assert co.ico and co.legal_form

    assert Product.__tablename__ == "uc_products"
    assert Order.__tablename__ == "uc_orders"
    assert Note.__tablename__ == "uc_notes"


def test_experiment_bookkeeping_is_not_persisted():
    """Experiment output and UC-02's PII answer key are files, not tables (D-DB-1).

    Guards the decision of 2026-09-03: the database holds CRM content only, so a
    future re-add of these entities has to be a deliberate choice rather than drift.
    """
    import substrate.schema.models as models

    for name in (
        "GeneratedMessage",
        "ErrorResult",
        "EvaluationRecord",
        "JudgeTestMessage",
        "PiiCorpusMessage",
        "PiiSpan",
    ):
        assert not hasattr(models, name), f"{name} is experiment bookkeeping, not CRM content"

    tables = set(SQLModel.metadata.tables)
    assert tables == {
        "uc_contacts",
        "uc_notes",
        "uc_change_log",  # what a model changed through UC-03: CRM record, not experiment output
        "uc_companies",
        "uc_products",
        "uc_orders",
        "uc_reviews",
        "uc_message_briefs",
        "uc_lifecycle_stages",
        "uc_recommendations",
        "uc_topics",
        "uc_aspects",
    }, f"unexpected table set: {sorted(tables)}"
