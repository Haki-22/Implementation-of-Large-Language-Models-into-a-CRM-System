"""
Integration tests for the unified snapshot loader (substrate/pipeline/build_substrate_db.py).

``rebuild_database()`` rebuilds the shared SQLite DB from JSON snapshots
in FK-dependency order. The DB holds CRM content only (D-DB-1, 2026-09-03):
Company, Contact, Product, Order, Note and MessageBrief.

These tests are self-contained: they generate small snapshots into a temp
directory (calling the generator functions directly with small n), then point
rebuild_database at that directory and assert row counts. No LLM calls are made.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helper — generate the snapshot files into a temp dir
# ---------------------------------------------------------------------------


async def _seed_snapshots(snapshot_dir: Path, *, seed: int = 1) -> None:
    """Generate small snapshot files for every snapshot-backed generator."""
    from substrate.generators.companies import generate_companies, save_snapshot as save_companies
    from substrate.generators.contacts import generate_contacts, save_snapshot as save_contacts

    snapshot_dir.mkdir(parents=True, exist_ok=True)
    (snapshot_dir / "contacts").mkdir(exist_ok=True)
    (snapshot_dir / "amazon").mkdir(exist_ok=True)
    (snapshot_dir / "briefs").mkdir(exist_ok=True)

    # Use a dummy thesis_dir structure for ocean_inferred
    mock_thesis = snapshot_dir / "mock_thesis"
    (mock_thesis / "ucs" / "uc01_personalization" / "snapshots").mkdir(parents=True, exist_ok=True)
    (mock_thesis / "ucs" / "uc01_personalization" / "snapshots" / "ocean_inferred.json").write_text(
        "[]", encoding="utf-8"
    )

    # Companies: the partner pool the contact generator affiliates with (registry fields seeded)
    companies = generate_companies(seed=seed)
    save_companies(companies, snapshot_dir / "contacts" / "companies.json", overwrite=True)

    # Contacts
    contacts = generate_contacts(seed=seed, n_clean=15, n_non_clean=5, n_foreign=2)
    save_contacts(contacts, snapshot_dir / "contacts" / "contacts.json")

    # Notes (the assembler requires the snapshot; it never fabricates notes)
    from substrate.generators.notes import generate_notes, save_snapshot as save_notes

    save_notes(
        generate_notes(contacts, seed=seed, n=6),
        snapshot_dir / "contacts" / "notes.json",
        overwrite=True,
    )

    # Mock reviewers and items
    (snapshot_dir / "amazon" / "amazon-translated-cz.json").write_text("[]", encoding="utf-8")
    (snapshot_dir / "amazon" / "amazon-original-en.json").write_text("[]", encoding="utf-8")
    (snapshot_dir / "amazon" / "amazon-catalog-en.json").write_text("[]", encoding="utf-8")
    (snapshot_dir / "amazon" / "amazon-catalog-titles-cs.json").write_text("{}", encoding="utf-8")

    # Message-briefs corpus
    import shutil
    from substrate.pipeline.build_substrate_db import BRIEFS

    shutil.copy(BRIEFS, snapshot_dir / "briefs" / "message_briefs.json")


def _ensure_notes_snapshot(snapshot_dir: Path, *, seed: int) -> None:
    """Mirror the chain: substrate.generators writes contacts, notes AND companies together.

    Tests that hand-build a snapshot dir with only the contacts file get the
    matching notes and companies snapshots here, so the assembler's "inputs are
    required" rule (covered by ``test_assemble_requires_notes_snapshot`` and
    ``test_assemble_requires_companies_snapshot``) does not make every other
    test seed them by hand.
    """
    from substrate.generators.companies import generate_companies, save_snapshot as save_companies
    from substrate.generators.notes import generate_notes, save_snapshot as save_notes

    contacts_path = snapshot_dir / "contacts" / "contacts.json"
    notes_path = snapshot_dir / "contacts" / "notes.json"
    companies_path = snapshot_dir / "contacts" / "companies.json"
    if not contacts_path.exists():
        return
    contacts = json.loads(contacts_path.read_text(encoding="utf-8"))
    if not notes_path.exists():
        save_notes(generate_notes(contacts, seed=seed, n=6), notes_path, overwrite=True)
    if not companies_path.exists():
        save_companies(generate_companies(seed=seed), companies_path, overwrite=True)


async def rebuild_database(
    db_path: str,
    snapshot_dir: str,
    *,
    force: bool = True,
    seed: int = 1,
    overwrite: bool = True,
    **kwargs,
):
    """Assemble and write the SQLite DB from ``snapshot_dir``, seeding missing snapshots first.

    Args:
        db_path: Where to write the SQLite file.
        snapshot_dir: Directory holding (or to receive) the JSON snapshots.
        force: Passed through to ``write_database`` (kept for call-site compatibility).
        seed: RNG seed used when snapshots must be generated.
        overwrite: Also forces ``write_database`` to replace an existing file.
        **kwargs: Accepted and ignored, for call-site compatibility.

    Returns:
        A dict of row counts per table (``uc_companies``, ``uc_contacts``, ...).
    """
    from substrate.pipeline.build_substrate_db import assemble, write_database

    snap = Path(snapshot_dir)
    _ensure_notes_snapshot(snap, seed=seed)
    try:
        data = assemble(snapshots_dir=snap, thesis_dir=snap / "mock_thesis")
    except FileNotFoundError:
        await _seed_snapshots(snap, seed=seed)
        data = assemble(snapshots_dir=snap, thesis_dir=snap / "mock_thesis")

    await write_database(data, Path(db_path), force=force or overwrite)
    return {
        "uc_companies": len(data["companies"]),
        "uc_contacts": len(data["contacts"]),
        "uc_products": len(data["products"]),
        "uc_orders": len(data["orders"]),
        "uc_reviews": len(data["reviews"]),
        "uc_message_briefs": len(data["briefs"]),
        "uc_notes": len(data["notes"]),
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_rebuild_loads_core_tables(tmp_path):
    """rebuild_database loads every core table from a temp snapshot dir."""
    snapshot_dir = tmp_path / "snapshots"
    asyncio.run(_seed_snapshots(snapshot_dir, seed=1))

    db = str(tmp_path / "t.db")
    counts = asyncio.run(rebuild_database(db_path=db, snapshot_dir=str(snapshot_dir), seed=1))

    assert isinstance(counts, dict)

    con = sqlite3.connect(db)
    try:
        n_companies = con.execute("SELECT COUNT(*) FROM uc_companies").fetchone()[0]
        n_contacts = con.execute("SELECT COUNT(*) FROM uc_contacts").fetchone()[0]
        n_briefs = con.execute("SELECT COUNT(*) FROM uc_message_briefs").fetchone()[0]
        n_notes = con.execute("SELECT COUNT(*) FROM uc_notes").fetchone()[0]
    finally:
        con.close()

    # The partner-company pool the generator draws from, so every contact
    # affiliation resolves to a real Company FK.
    assert n_companies >= 4
    assert n_contacts > 0
    assert n_briefs > 0  # the brief corpus is a committed snapshot, always populated
    assert n_notes > 0

    # Returned counts dict mirrors what landed in the DB.
    assert counts["uc_companies"] == n_companies
    assert counts["uc_contacts"] == n_contacts
    assert counts["uc_message_briefs"] == n_briefs
    assert counts["uc_notes"] == n_notes


def test_write_database_rejects_out_of_scale_ocean(tmp_path):
    """The assembler validates every OCEAN profile on its way into the database.

    Guards the decision of 2026-09-03: ``Contact.set_ocean`` is the only range
    check in the schema and it must run at build time, so a sampled or
    LLM-inferred value outside the 1-5 BFI scale fails the rebuild instead of
    entering the database unnoticed.
    """
    snapshot_dir = tmp_path / "snapshots"
    asyncio.run(_seed_snapshots(snapshot_dir, seed=1))
    contacts_path = snapshot_dir / "contacts" / "contacts.json"
    contacts = json.loads(contacts_path.read_text(encoding="utf-8"))
    contacts[0]["ocean"] = {"O": 5.5, "C": 3.0, "E": 3.0, "A": 3.0, "N": 3.0}
    contacts_path.write_text(json.dumps(contacts, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="outside"):
        asyncio.run(
            rebuild_database(db_path=str(tmp_path / "t.db"), snapshot_dir=str(snapshot_dir), seed=1)
        )


def test_frequent_words_drop_stop_words_and_keep_content():
    """The lexicon carries the customer's content words, not Czech grammar (Q5, 2026-09-03)."""
    from substrate.pipeline.build_substrate_db import _czech_frequent_words

    reviews = [
        {"summary": "Kabel funguje, protože je kabel dobrý", "reviewText": "než kabel, pokud usb"}
    ]
    words = json.loads(_czech_frequent_words(reviews))
    assert words[0] == "kabel"
    assert not {"protože", "než", "pokud"} & set(words)


def test_prior_interactions_take_the_most_recent_reviews():
    """prior_interactions is the newest history, not the first reviews by product id (Q6, 2026-09-03)."""
    from substrate.pipeline.build_substrate_db import _prior_interactions

    reviews = [
        {"summary": "starý", "overall": 3.0, "unixReviewTime": 1000},
        {"summary": "nový", "overall": 5.0, "unixReviewTime": 3000},
        {"summary": "střední", "overall": 4.0, "unixReviewTime": 2000},
    ]
    assert _prior_interactions(reviews, limit=2) == "[hodnocení 5.0] nový\n[hodnocení 4.0] střední"


def test_rebuild_resolves_contact_company_fk(tmp_path):
    """Contacts with a company affiliation resolve to a real Company FK."""
    snapshot_dir = tmp_path / "snapshots"
    asyncio.run(_seed_snapshots(snapshot_dir, seed=2))

    db = str(tmp_path / "fk.db")
    asyncio.run(rebuild_database(db_path=db, snapshot_dir=str(snapshot_dir), seed=2))

    con = sqlite3.connect(db)
    try:
        # Every non-NULL company_id on a contact must point to a real company.
        orphans = con.execute(
            "SELECT COUNT(*) FROM uc_contacts c "
            "WHERE c.company_id IS NOT NULL "
            "AND c.company_id NOT IN (SELECT id FROM uc_companies)"
        ).fetchone()[0]
    finally:
        con.close()

    assert orphans == 0


def test_rebuild_replaces_existing_database_instead_of_appending(tmp_path):
    """Running rebuild_database twice leaves one clean copy of each table."""
    snapshot_dir = tmp_path / "snapshots"
    asyncio.run(_seed_snapshots(snapshot_dir, seed=5))

    db = str(tmp_path / "idempotent.db")
    first_counts = asyncio.run(rebuild_database(db_path=db, snapshot_dir=str(snapshot_dir), seed=5))
    second_counts = asyncio.run(
        rebuild_database(db_path=db, snapshot_dir=str(snapshot_dir), seed=5, overwrite=True)
    )

    con = sqlite3.connect(db)
    try:
        table_counts = {
            "uc_companies": con.execute("SELECT COUNT(*) FROM uc_companies").fetchone()[0],
            "uc_contacts": con.execute("SELECT COUNT(*) FROM uc_contacts").fetchone()[0],
            "uc_message_briefs": con.execute("SELECT COUNT(*) FROM uc_message_briefs").fetchone()[
                0
            ],
            "uc_products": con.execute("SELECT COUNT(*) FROM uc_products").fetchone()[0],
            "uc_orders": con.execute("SELECT COUNT(*) FROM uc_orders").fetchone()[0],
            "uc_reviews": con.execute("SELECT COUNT(*) FROM uc_reviews").fetchone()[0],
            "uc_notes": con.execute("SELECT COUNT(*) FROM uc_notes").fetchone()[0],
        }
    finally:
        con.close()

    assert second_counts == first_counts
    assert table_counts == second_counts


def test_rebuild_refuses_existing_database_without_overwrite(tmp_path):
    """rebuild_database refuses to replace an existing DB unless requested."""
    snapshot_dir = tmp_path / "snapshots"
    asyncio.run(_seed_snapshots(snapshot_dir, seed=6))

    db = str(tmp_path / "protected.db")
    asyncio.run(rebuild_database(db_path=db, snapshot_dir=str(snapshot_dir), seed=6))

    try:
        asyncio.run(
            rebuild_database(
                db_path=db, snapshot_dir=str(snapshot_dir), seed=6, force=False, overwrite=False
            )
        )
    except FileExistsError as exc:
        assert "exists" in str(exc)
    else:  # pragma: no cover - makes the failure message clearer
        raise AssertionError("rebuild_database overwrote an existing DB without overwrite=True")


def test_snapshot_roundtrip_preserves_company_fk(tmp_path):
    """Contact company_id survives the full generate → snapshot → rebuild round-trip.

    Verifies the fix for the lossy-snapshot bug: save_snapshot used to strip
    _company_name, leaving company_id NULL after a snapshot reload.  Now it
    promotes _company_name to the public key company_name so rebuild_database
    can resolve the FK from disk.
    """
    from substrate.generators.contacts import generate_contacts, save_snapshot as save_contacts
    from substrate.generators.companies import generate_companies, save_snapshot as save_companies

    snapshot_dir = tmp_path / "snapshots"
    snapshot_dir.mkdir()
    (snapshot_dir / "contacts").mkdir()
    (snapshot_dir / "amazon").mkdir()
    (snapshot_dir / "briefs").mkdir()
    mock_thesis = snapshot_dir / "mock_thesis"
    (mock_thesis / "ucs" / "uc01_personalization" / "snapshots").mkdir(parents=True, exist_ok=True)
    (mock_thesis / "ucs" / "uc01_personalization" / "snapshots" / "ocean_inferred.json").write_text(
        "[]", encoding="utf-8"
    )
    (snapshot_dir / "amazon" / "amazon-translated-cz.json").write_text("[]", encoding="utf-8")
    (snapshot_dir / "amazon" / "amazon-original-en.json").write_text("[]", encoding="utf-8")
    (snapshot_dir / "amazon" / "amazon-catalog-en.json").write_text("[]", encoding="utf-8")
    (snapshot_dir / "amazon" / "amazon-catalog-titles-cs.json").write_text("{}", encoding="utf-8")

    import shutil
    from substrate.pipeline.build_substrate_db import BRIEFS

    shutil.copy(BRIEFS, snapshot_dir / "briefs" / "message_briefs.json")

    # Generate contacts with seed that produces some company affiliations (~50%).
    # Use enough contacts so that at least one company affiliation is generated.
    seed = 7
    companies = generate_companies(seed=seed, n=5)
    save_companies(companies, snapshot_dir / "companies.json")

    contacts = generate_contacts(seed=seed, n_clean=30, n_non_clean=5, n_foreign=2)
    # Confirm that at least one in-memory contact has a company affiliation,
    # otherwise the test proves nothing.
    assert any(c.get("_company_name") for c in contacts), (
        "Test setup: no contact with _company_name was generated; "
        "increase n_clean or change the seed."
    )

    # Write the snapshot — this is the step that previously lost _company_name.
    contacts_snap_path = snapshot_dir / "contacts" / "contacts.json"
    save_contacts(contacts, contacts_snap_path)

    # Confirm the snapshot file now contains the public company_name key.
    with contacts_snap_path.open(encoding="utf-8") as fh:
        snap_contacts = json.load(fh)
    assert any(c.get("company_name") for c in snap_contacts), (
        "save_snapshot did not write company_name into the snapshot JSON."
    )

    # Rebuild the DB from the snapshot files on disk.
    db = str(tmp_path / "roundtrip.db")
    asyncio.run(rebuild_database(db_path=db, snapshot_dir=str(snapshot_dir), seed=seed))

    con = sqlite3.connect(db)
    try:
        n_with_company = con.execute(
            "SELECT COUNT(*) FROM uc_contacts WHERE company_id IS NOT NULL"
        ).fetchone()[0]
        orphans = con.execute(
            "SELECT COUNT(*) FROM uc_contacts c "
            "WHERE c.company_id IS NOT NULL "
            "AND c.company_id NOT IN (SELECT id FROM uc_companies)"
        ).fetchone()[0]
    finally:
        con.close()

    assert n_with_company > 0, (
        "No uc_contacts row has a non-NULL company_id after snapshot round-trip; "
        "the company FK was lost during save_snapshot or _contact_row_from_dict."
    )
    assert orphans == 0, "company_id FK constraint violated after snapshot round-trip."


def test_rebuild_generates_missing_snapshots(tmp_path):
    """rebuild_database succeeds even when no snapshot files exist."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    db = str(tmp_path / "gen.db")
    counts = asyncio.run(
        rebuild_database(
            db_path=db,
            snapshot_dir=str(empty_dir),
            seed=3,
            n_contacts=20,
        )
    )

    con = sqlite3.connect(db)
    try:
        n_contacts = con.execute("SELECT COUNT(*) FROM uc_contacts").fetchone()[0]
        n_companies = con.execute("SELECT COUNT(*) FROM uc_companies").fetchone()[0]
        n_briefs = con.execute("SELECT COUNT(*) FROM uc_message_briefs").fetchone()[0]
    finally:
        con.close()

    assert n_contacts > 0
    assert n_companies > 0
    assert n_briefs > 0
    assert counts["uc_contacts"] == n_contacts
    assert counts["uc_message_briefs"] == n_briefs

    # The missing snapshot files should have been written into snapshot_dir.
    assert (empty_dir / "contacts" / "companies.json").exists()
    assert (empty_dir / "contacts" / "contacts.json").exists()
    assert (empty_dir / "briefs" / "message_briefs.json").exists()


def test_assemble_requires_notes_snapshot(tmp_path):
    """The assembler never fabricates notes: a missing snapshot is an error."""
    import pytest

    from substrate.pipeline.build_substrate_db import assemble

    snapshot_dir = tmp_path / "snapshots"
    asyncio.run(_seed_snapshots(snapshot_dir, seed=4))
    (snapshot_dir / "contacts" / "notes.json").unlink()

    with pytest.raises(FileNotFoundError, match="notes snapshot missing"):
        assemble(snapshots_dir=snapshot_dir, thesis_dir=snapshot_dir / "mock_thesis")


def test_assemble_requires_companies_snapshot(tmp_path):
    """The assembler never invents companies: a missing snapshot is an error."""
    import pytest

    from substrate.pipeline.build_substrate_db import assemble

    snapshot_dir = tmp_path / "snapshots"
    asyncio.run(_seed_snapshots(snapshot_dir, seed=4))
    (snapshot_dir / "contacts" / "companies.json").unlink()

    with pytest.raises(FileNotFoundError, match="companies snapshot missing"):
        assemble(snapshots_dir=snapshot_dir, thesis_dir=snapshot_dir / "mock_thesis")


def test_assemble_rejects_unknown_company_affiliation(tmp_path):
    """A contact affiliated with a company absent from the snapshot fails loudly."""
    import pytest

    from substrate.pipeline.build_substrate_db import assemble

    snapshot_dir = tmp_path / "snapshots"
    asyncio.run(_seed_snapshots(snapshot_dir, seed=4))
    companies_path = snapshot_dir / "contacts" / "companies.json"
    companies = json.loads(companies_path.read_text(encoding="utf-8"))
    companies_path.write_text(json.dumps(companies[:1], ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="missing from the snapshot"):
        assemble(snapshots_dir=snapshot_dir, thesis_dir=snapshot_dir / "mock_thesis")


def test_companies_carry_registry_fields(tmp_path):
    """uc_companies rows come from the snapshot with IČO, DIČ, address and legal form filled."""
    from utils.czech_identifiers import is_valid_ico

    snapshot_dir = tmp_path / "snapshots"
    asyncio.run(_seed_snapshots(snapshot_dir, seed=2))
    db = str(tmp_path / "companies.db")
    asyncio.run(rebuild_database(db_path=db, snapshot_dir=str(snapshot_dir), seed=2))

    con = sqlite3.connect(db)
    try:
        rows = con.execute(
            "SELECT name, ico, dic, city, postal_code, legal_form FROM uc_companies"
        ).fetchall()
        dangling = con.execute(
            "SELECT COUNT(*) FROM uc_contacts WHERE company_id IS NOT NULL "
            "AND company_id NOT IN (SELECT id FROM uc_companies)"
        ).fetchone()[0]
    finally:
        con.close()

    assert len(rows) == 8
    assert dangling == 0
    for name, ico, dic, city, postal_code, legal_form in rows:
        assert is_valid_ico(ico)
        assert dic == "CZ" + ico
        assert city and postal_code
        assert name.endswith(" " + legal_form)


def test_rebuild_loads_note_snapshot(tmp_path):
    """Note rows load from the committed notes snapshot under contacts/."""
    snapshot_dir = tmp_path / "snapshots"
    asyncio.run(_seed_snapshots(snapshot_dir, seed=9))

    notes = [
        {
            "contact_id": 1,
            "content": "Customer asked for a concise follow-up.",
            "category": "follow_up",
            "created_at": "2026-05-28T08:30:00",
            "pseudonymized": False,
        },
        {
            "contact_id": 2,
            "content": "Send warranty details to jan.novak@example.cz.",
            "category": "support",
            "created_at": "2026-05-27T12:00:00",
            "pseudonymized": True,
        },
    ]
    (snapshot_dir / "contacts" / "notes.json").write_text(
        json.dumps(notes, ensure_ascii=False), encoding="utf-8"
    )

    db = str(tmp_path / "notes.db")
    counts = asyncio.run(rebuild_database(db_path=db, snapshot_dir=str(snapshot_dir), seed=9))

    con = sqlite3.connect(db)
    try:
        rows = con.execute(
            "SELECT contact_id, category, pseudonymized FROM uc_notes ORDER BY id"
        ).fetchall()
        orphans = con.execute(
            "SELECT COUNT(*) FROM uc_notes n WHERE n.contact_id NOT IN (SELECT id FROM uc_contacts)"
        ).fetchone()[0]
    finally:
        con.close()

    assert counts["uc_notes"] == 2
    assert rows == [(1, "follow_up", 0), (2, "support", 1)]
    assert orphans == 0


def test_assemble_does_not_keep_english_fallback_without_czech_reviews(tmp_path):
    """A reviewer with zero Czech reviews must not leak English snapshot values into the DB."""
    from substrate.pipeline.build_substrate_db import assemble

    snap = tmp_path / "snap"
    asyncio.run(_seed_snapshots(snap, seed=1))
    contacts_path = snap / "contacts" / "contacts.json"
    contact = json.loads(contacts_path.read_text(encoding="utf-8"))[0]
    contact["reviewer_id"] = "R1"
    contact["amazon_group"] = "B"
    contact["frequent_words"] = json.dumps(["can", "your", "just"])
    contact["prior_interactions"] = "[asin=B1; rating=4.0; time=1] english text"
    contacts_path.write_text(json.dumps([contact]), encoding="utf-8")
    (snap / "amazon" / "amazon-translated-cz.json").write_text(
        json.dumps([{"reviewerID": "R1", "group": "B", "reviews": []}]), encoding="utf-8"
    )

    data = assemble(snapshots_dir=snap, thesis_dir=snap / "mock_thesis")

    assert data["contacts_without_czech"] == ["R1"]
    assert data["contacts"][0]["frequent_words"] is None
    assert data["contacts"][0]["prior_interactions"] is None


def test_reviews_table_mirrors_orders_and_carries_both_languages(tmp_path):
    """One uc_reviews row per order, English always, Czech only where the translation exists (D-DB-3).

    Also checks the three prompt digests on the contact come from the same
    reviews, and that the FTS5 index finds a Czech word with its diacritics folded.
    """
    from substrate.constants import REVIEWS_FTS_TABLE, STYLE_EXCERPT_CHARS
    from substrate.pipeline.build_substrate_db import assemble, write_database

    snap = tmp_path / "snap"
    asyncio.run(_seed_snapshots(snap, seed=1))
    contacts_path = snap / "contacts" / "contacts.json"
    contact = json.loads(contacts_path.read_text(encoding="utf-8"))[0]
    contact["reviewer_id"] = "R1"
    contact["amazon_group"] = "B"
    contacts_path.write_text(json.dumps([contact]), encoding="utf-8")

    long_body = "Tento kabel je výborný, " * 40  # > STYLE_EXCERPT_CHARS, no gendered form
    gendered_body = "Koupil jsem si ho a byl jsem nadšený, " * 60  # longer, but masculine
    en_reviews = [
        {
            "asin": "B1",
            "overall": 5.0,
            "helpful": [2, 3],
            "unixReviewTime": 1_300_000_000,
            "summary": "Great cable",
            "reviewText": "This cable is excellent.",
        },
        {
            "asin": "B2",
            "overall": 3.0,
            "helpful": [0, 0],
            "unixReviewTime": 1_400_000_000,
            "summary": "Meh",
            "reviewText": "Untranslated body.",
        },
        {
            "asin": "B3",
            "overall": 4.0,
            "helpful": [1, 1],
            "unixReviewTime": 1_350_000_000,
            "summary": "Nice",
            "reviewText": "I bought it and was thrilled.",
        },
    ]
    cz_reviews = [
        {**en_reviews[0], "summary": "Skvělý kabel", "reviewText": long_body},
        {**en_reviews[2], "summary": "Pěkné", "reviewText": gendered_body},
    ]
    (snap / "amazon" / "amazon-original-en.json").write_text(
        json.dumps([{"reviewerID": "R1", "group": "B", "reviews": en_reviews}]), encoding="utf-8"
    )
    (snap / "amazon" / "amazon-translated-cz.json").write_text(
        json.dumps([{"reviewerID": "R1", "group": "B", "reviews": cz_reviews}]), encoding="utf-8"
    )
    (snap / "amazon" / "amazon-catalog-en.json").write_text(
        json.dumps(
            [
                {"asin": "B1", "title": "Cable", "price": 10},
                {"asin": "B2", "title": "Box"},
                {"asin": "B3", "title": "Thing"},
            ]
        ),
        encoding="utf-8",
    )
    (snap / "amazon" / "amazon-catalog-titles-cs.json").write_text(
        json.dumps({"B1": "Kabel"}), encoding="utf-8"
    )
    # UC-04's committed result for this reviewer: loaded into the tables, re-keyed to the contact.
    handoff = snap / "mock_thesis" / "ucs" / "uc04_matchmaker" / "results"
    handoff.mkdir(parents=True, exist_ok=True)
    (handoff / "uc04_to_uc01_handoff.json").write_text(
        json.dumps(
            {
                "users": {
                    "R1": {
                        "topk_recommendations": [
                            {
                                "asin": "B2",
                                "title": "Box",
                                "score": 0.5,
                                "reason": "Hodí se.",
                                "evidence_asin": ["B1"],
                            },
                            {
                                "asin": "ZZZ",
                                "title": "Unknown",
                                "score": None,
                                "reason": "Mimo katalog.",
                            },
                        ],
                        "topic_clusters": [
                            {
                                "label": "kabely / hdmi",
                                "weight": 0.3,
                                "evidence_titles": ["Cable"],
                                "_paradigm": "lda",
                            }
                        ],
                        "lifecycle": {"stage": "ignored_here"},
                        "absa": {
                            "aspects": [
                                {"aspect": "cena", "sentiment": "negative", "evidence": "drahé"}
                            ]
                        },
                    },
                    "R-nobody": {"topk_recommendations": [{"asin": "B1"}]},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    data = assemble(snapshots_dir=snap, thesis_dir=snap / "mock_thesis")
    db = tmp_path / "reviews.db"
    asyncio.run(write_database(data, db, force=True))

    assert len(data["reviews"]) == len(data["orders"]) == 3
    assert data["reviews_translated"] == 2
    # The style sample skips the longer masculine body and takes the clean one,
    # cut at a word boundary (the 600th character here falls on a space).
    assert data["contacts"][0]["style_excerpt"] == long_body[:STYLE_EXCERPT_CHARS].rstrip()
    # Headlines come from the Czech reviews only, newest first; B2 has no translation.
    assert (
        data["contacts"][0]["prior_interactions"]
        == "[hodnocení 4.0] Pěkné\n[hodnocení 5.0] Skvělý kabel"
    )
    # Last order 2014-05-13, 71 days before the reference date 2014-07-23 -> active.
    assert data["contacts"][0]["lifecycle_stage"] == "active"
    assert (len(data["recommendations"]), len(data["topics"]), len(data["aspects"])) == (2, 1, 1)

    con = sqlite3.connect(db)
    try:
        rows = con.execute(
            "SELECT r.order_id, o.id, r.product_id, o.product_id, r.rating, r.helpful_up, "
            "r.helpful_total, r.text_en, r.summary_cs, r.text_cs "
            "FROM uc_reviews r JOIN uc_orders o ON o.id = r.order_id ORDER BY r.id"
        ).fetchall()
        excerpt, stage = con.execute(
            "SELECT style_excerpt, lifecycle_stage FROM uc_contacts"
        ).fetchone()
        label = con.execute(
            "SELECT s.label_cs FROM uc_contacts c JOIN uc_lifecycle_stages s ON s.code = c.lifecycle_stage"
        ).fetchone()[0]
        names = con.execute("SELECT sku, name, name_cs FROM uc_products ORDER BY id").fetchall()
        recs = con.execute(
            "SELECT rank, asin, product_id, score, reason_cs FROM uc_recommendations ORDER BY rank"
        ).fetchall()
        topic = con.execute("SELECT label, weight, paradigm FROM uc_topics").fetchone()
        aspect = con.execute("SELECT aspect, sentiment, evidence FROM uc_aspects").fetchone()
        fts_hits = con.execute(
            f"SELECT count(*) FROM {REVIEWS_FTS_TABLE} WHERE {REVIEWS_FTS_TABLE} MATCH 'vyborny'"
        ).fetchone()[0]
        fts_prefix = con.execute(
            f"SELECT count(*) FROM {REVIEWS_FTS_TABLE} WHERE {REVIEWS_FTS_TABLE} MATCH 'cabl*'"
        ).fetchone()[0]
    finally:
        con.close()

    assert [(r[0], r[1], r[2], r[3]) for r in rows] == [(1, 1, 1, 1), (2, 2, 2, 2), (3, 3, 3, 3)]
    assert rows[0][4:7] == (5.0, 2, 3)
    assert rows[0][7] == "This cable is excellent." and rows[0][8] == "Skvělý kabel"
    assert rows[0][9] == long_body
    assert rows[1][8] is None and rows[1][9] is None, (
        "untranslated reviews stay NULL, never English"
    )
    assert excerpt == long_body[:STYLE_EXCERPT_CHARS].rstrip()
    assert stage == "active" and label == "aktivní zákazník"
    assert names == [("B1", "Cable", "Kabel"), ("B2", "Box", None), ("B3", "Thing", None)]
    assert recs == [(1, "B2", 2, 0.5, "Hodí se."), (2, "ZZZ", None, None, "Mimo katalog.")]
    assert topic == ("kabely / hdmi", 0.3, "lda")
    assert aspect == ("cena", "negative", "drahé")
    assert fts_hits == 1, "diacritics are folded: 'vyborny' finds 'výborný'"
    assert fts_prefix == 1, "prefix query finds 'cable'"


def test_ocean_source_is_persisted_and_consistent(tmp_path):
    """ocean_source says where each profile came from and is NULL exactly when there is no profile."""
    snapshot_dir = tmp_path / "snapshots"
    asyncio.run(_seed_snapshots(snapshot_dir, seed=3))
    db = str(tmp_path / "ocean.db")
    asyncio.run(rebuild_database(db_path=db, snapshot_dir=str(snapshot_dir), seed=3))

    con = sqlite3.connect(db)
    try:
        rows = con.execute("SELECT ocean, ocean_source FROM uc_contacts").fetchall()
    finally:
        con.close()

    assert rows
    for ocean, source in rows:
        has_profile = ocean not in (None, "null")
        assert (source in ("synthetic", "inferred")) == has_profile


def test_style_excerpt_filters_every_first_person_past_form_and_falls_back():
    """D-DB-6: the everyday vowel forms count, and a contact with no clean body keeps a stripped sample."""
    from substrate.pipeline.build_substrate_db import _GENDERED_FIRST_PERSON, _style_excerpt

    for text in (
        "Koupil jsem si je",
        "Takže jsem používal obě verze",
        "koupila jsem",
        "řekl jsem",
        "byl bych rád",
    ):
        assert _GENDERED_FIRST_PERSON.search(text), text
    assert not _GENDERED_FIRST_PERSON.search("Zvuk je čistý a basy hluboké.")

    clean = "Zvuk je čistý a basy hluboké. Baterie vydrží celý den."
    reviews = [
        {"reviewText": "Koupil jsem si tento reproduktor minulý týden. " + clean},
        {"reviewText": "Používal jsem ho týden."},
    ]
    # No whole body is clean: the longest body minus its gendered sentences.
    assert _style_excerpt(reviews) == clean
    # A clean whole body always wins over a stripped one, even when shorter.
    reviews.append({"reviewText": "Dobrý zvuk."})
    assert _style_excerpt(reviews) == "Dobrý zvuk."
    # Nothing survives -> no sample, never English.
    assert _style_excerpt([{"reviewText": "Koupil jsem ho."}]) is None
