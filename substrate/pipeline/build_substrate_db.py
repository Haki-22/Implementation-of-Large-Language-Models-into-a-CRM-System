"""Assemble the canonical CRM substrate DB from clean snapshots.

This is pure assembly: every row is sourced from a versioned snapshot, nothing
is fabricated.

The database holds **CRM content** -- contacts, their notes, their employer,
the catalogue, the purchase history, the reviews behind it in both languages, and
the operator's message briefs. Experiment output (generated messages, error rows,
evaluation records, judge fixtures) and UC-02's PII answer key are not tables:
they live in committed JSON/CSV next to the run that produced them, so the thesis
numbers reproduce without this git-ignored database. See
``substrate/schema/models.py`` for the full rationale.

Inputs (all read-only)
----------------------
- ``substrate/snapshots/contacts/contacts.json`` -- 500 Faker Czech
  identities (name, vocative, gender, formality, synthetic OCEAN, ``reviewer_id``).
- ``substrate/snapshots/contacts/notes.json`` -- 80 seeded Czech CRM notes
  (``substrate/generators/notes/``), the writable surface UC-03 works on.
- ``substrate/snapshots/contacts/companies.json`` -- the 8 partner companies
  with registry fields (``substrate/generators/companies.py``); ``Contact.company_id`` is
  resolved by name against it and an unknown affiliation is an error.
- ``ucs/uc01_personalization/snapshots/ocean_inferred.json`` -- BFI-2 OCEAN
  profiles a model inferred from the reviewer's English reviews (every linked
  contact since the 2026-09-06 rerun; written by ``ocean_inference freeze`` from
  run folders); overrides the sampled value for those, with an ``ocean_source``
  provenance flag.
- ``substrate/snapshots/amazon/amazon-original-en.json`` -- the reviewer's English
  reviews: one order and one ``uc_reviews`` row per review.
- ``substrate/snapshots/amazon/amazon-translated-cz.json`` -- the same reviews in
  Czech (frozen translation), joined to the English row by item; source of the
  Czech columns of ``uc_reviews`` and of each contact's three prompt digests
  (``frequent_words``, ``prior_interactions``, ``style_excerpt``).
- ``substrate/snapshots/amazon/amazon-catalog-en.json`` -- product catalogue.
- ``substrate/snapshots/briefs/message_briefs.json`` -- the 25 operator message briefs.

Output
------
- ``substrate/snapshots/substrate.db`` -- the seven CRM-content tables of
  ``substrate/schema/models.py`` (contacts, notes, companies, products, orders,
  reviews, message briefs), plus the lifecycle-stage vocabulary and UC-04's
  recommendations / topics / aspects tables (empty until UC-04 has run), plus
  the FTS5 full-text index ``uc_reviews_fts`` over the review text.

Run:
    python -m substrate.pipeline.build_substrate_db --force   # build_all step ``database``
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from substrate.constants import (
    LIFECYCLE_STAGES,
    REVIEWS_FTS_TABLE,
    STYLE_EXCERPT_CHARS,
    SUBSTRATE_REFERENCE_DATE,
)
from substrate.lifecycle import stage_from_dates
from substrate.schema.models import (
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

from utils.file_safety import require_can_write
from utils.paths import (
    BRIEFS_SNAPSHOT as BRIEFS,
    CATALOG_EN as ITEMS_EN,
    CATALOG_TITLES_CS,
    CONTACTS_SNAPSHOT,
    COMPANIES_SNAPSHOT,
    NOTES_SNAPSHOT,
    REVIEWERS_CZ_SNAPSHOT as REVIEWERS_CZ,
    REVIEWERS_EN_SNAPSHOT as REVIEWERS_EN,
    SNAPSHOTS_DIR as SNAPSHOTS,
    SUBSTRATE_DATA_DIR,
    SUBSTRATE_DB as DEFAULT_DB,
    THESIS_ROOT as THESIS_DIR,
    UC04_HANDOFF,
)

# Catalogue prices are the Amazon USD list prices converted with one fixed nominal rate
# (roughly the 2024-2025 CZK/USD level). No metric in the thesis uses the absolute price;
# the constant only gives the Czech CRM a plausible currency scale.
USD_TO_CZK = 23.0
OCEAN_KEYS = ("O", "C", "E", "A", "N")

# The stop-list behind ``Contact.frequent_words``. A hand-typed set of 69 words
# was used until 2026-09-03; measured over all 411 lexicons it let function words
# through (``než`` in 373 of them, ``pokud`` 365, ``takže`` 271, ``protože`` 243,
# ``být`` 114), so half of a typical top-12 said nothing about the customer. The
# list is now the Czech stop-word list of the stopwords-iso project, vendored
# with its provenance in ``substrate/data/cz_stopwords.txt`` so a reader can check every
# word and the build does not depend on a package version.
STOPWORDS_PATH = SUBSTRATE_DATA_DIR / "cz_stopwords.txt"


def _load_stopwords(path: Path = STOPWORDS_PATH) -> frozenset[str]:
    """Read the vendored stop-word list, skipping its ``#`` provenance header."""
    return frozenset(
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    )


CZECH_STOPWORDS = _load_stopwords()


# ---------------------------------------------------------------------------
# Czech derivations
# ---------------------------------------------------------------------------


def _czech_frequent_words(reviews: list[dict[str, Any]], *, limit: int = 20) -> str | None:
    """Top ``limit`` content words across a reviewer's Czech review text + summaries.

    The lexicon is what UC-01 pastes into a prompt as the customer's frequent
    words, so it has to carry content words, not grammar: tokens are lower-cased
    surface forms (no lemmatisation, so the customer's own word forms survive),
    at least three characters long and not in the vendored stop-list. The cap of
    20 is the number UC-01's prompt formatter pastes (``prompts_uc01._format_frequent_words``);
    it was 12 until 2026-09-03, raised so the intensifiers a customer uses do not
    crowd out the content words.
    """
    text = " ".join(
        " ".join(part for part in (r.get("summary") or "", r.get("reviewText") or "") if part)
        for r in reviews
    ).lower()
    words = [
        word
        for word in re.findall(r"[a-zá-žäöü][a-zá-ž0-9]{2,}", text)
        if word not in CZECH_STOPWORDS
    ]
    if not words:
        return None
    return json.dumps([w for w, _ in Counter(words).most_common(limit)], ensure_ascii=False)


def _prior_interactions(reviews: list[dict[str, Any]], *, limit: int = 6) -> str | None:
    """The ``limit`` most recent review headlines, newest first, one per line with the rating.

    This is the customer's recent history as a salesperson would see it. The
    reviews arrive sorted by product id, so taking the first ones picked an
    arbitrary, old sample (decision Q6, 2026-09-03); sorting by review time keeps
    the field anchored to the substrate's reference date, the day of the last order.
    """
    recent = sorted(reviews, key=lambda r: int(r.get("unixReviewTime") or 0), reverse=True)
    rows = []
    for r in recent[:limit]:
        summary = (r.get("summary") or "").strip()
        if summary:
            rows.append(f"[hodnocení {r.get('overall')}] {summary}")
    return "\n".join(rows) if rows else None


# Czech first-person forms that reveal the speaker's gender: "koupil jsem" /
# "jsem koupil" / "byl bych" (masculine), "koupila jsem" / "byla" (feminine),
# plus rád / ráda and sám / sama. The translation writes them masculine for
# almost every reviewer regardless of who wrote the original, so a style
# sample that contains one would tell the model to write a woman as a man.
#
# D-DB-6 (user 2026-09-04): any word ending in "-l" / "-la" next to jsem / bych
# counts. Until that date the masculine branch demanded a consonant before the
# "-l" (řekl, mohl), so the everyday vowel forms (koupil, používal, měl) passed:
# 138 of 407 samples carried a first-person past form, 68 of them a masculine
# one behind a woman. A noun in "-l" next to "jsem" ("kabel jsem koupil") also
# matches now, which only makes the filter stricter.
_GENDERED_FIRST_PERSON = re.compile(
    r"(\b\w+la?\b\s+(?:\w+\s+)?(?:jsem|bych))"
    r"|(\b(?:jsem|bych)\s+(?:\w+\s+)?\w+la?\b)"
    r"|\b(?:rád|ráda|sám|sama|byl|byla)\b",
    re.IGNORECASE,
)

# Sentence boundary for the D-DB-6 fallback: a terminal mark followed by space.
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def _style_excerpt(
    reviews: list[dict[str, Any]], *, limit: int = STYLE_EXCERPT_CHARS
) -> str | None:
    """The longest Czech review body with no gendered first-person form, cut to ``limit``.

    UC-01's style-mirroring prompt needs a sample of the customer's own prose
    (the six headlines in ``prior_interactions`` are too short to carry style);
    the longest body is the richest sample. Bodies with a gendered first-person
    form are skipped: the translator renders "I bought" as masculine for 377 of
    410 reviewers whoever wrote it, so such a sample would carry the wrong gender
    into the message for most women.

    D-DB-6 (user 2026-09-04, option B of two measured): when *every* body of a
    contact carries a gendered form, the sample is the longest body with those
    sentences cut out rather than nothing, so the contact keeps its place in the
    UC-01 reading set. On the built substrate 388 contacts get a whole body and
    22 the stripped form (410 = every contact with a Czech body); no woman's
    sample carries a masculine form. The
    style-match metric does not use this column; it reads all of the contact's
    reviews.
    """
    bodies = [b for b in ((r.get("reviewText") or "").strip() for r in reviews) if b]
    neutral = [b for b in bodies if not _GENDERED_FIRST_PERSON.search(b)]
    if neutral:
        return _cut(max(neutral, key=len), limit)
    stripped = (
        " ".join(s for s in _SENTENCE_END.split(b) if not _GENDERED_FIRST_PERSON.search(s))
        for b in bodies
    )
    longest = max(stripped, key=len, default="")
    return _cut(longest, limit) or None


def _cut(text: str, limit: int) -> str:
    """``text`` cut to at most ``limit`` characters at a word boundary, so no word is torn."""
    if len(text) <= limit:
        return text
    head = text[:limit]
    return (head.rsplit(" ", 1)[0] if " " in head else head).rstrip()


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def assemble(snapshots_dir: Path = SNAPSHOTS, thesis_dir: Path = THESIS_DIR) -> dict[str, Any]:
    """Load every committed snapshot and derive the rows of each table in memory (no DB writes)."""
    contacts_path = snapshots_dir / "contacts" / CONTACTS_SNAPSHOT.name
    notes_path = snapshots_dir / "contacts" / NOTES_SNAPSHOT.name
    companies_path = snapshots_dir / "contacts" / COMPANIES_SNAPSHOT.name
    ocean_inferred_path = (
        thesis_dir / "ucs" / "uc01_personalization" / "snapshots" / "ocean_inferred.json"
    )
    reviewers_cz_path = snapshots_dir / "amazon" / REVIEWERS_CZ.name
    reviewers_en_path = snapshots_dir / "amazon" / REVIEWERS_EN.name
    items_en_path = snapshots_dir / "amazon" / ITEMS_EN.name
    titles_cs_path = snapshots_dir / "amazon" / CATALOG_TITLES_CS.name
    briefs_path = snapshots_dir / "briefs" / BRIEFS.name
    handoff_path = thesis_dir / "ucs" / "uc04_matchmaker" / "results" / UC04_HANDOFF.name

    contacts = json.loads(contacts_path.read_text(encoding="utf-8"))
    ocean_inferred = json.loads(ocean_inferred_path.read_text(encoding="utf-8"))
    reviewers_cz = {
        u["reviewerID"]: u for u in json.loads(reviewers_cz_path.read_text(encoding="utf-8"))
    }
    reviewers_en = {
        u["reviewerID"]: u for u in json.loads(reviewers_en_path.read_text(encoding="utf-8"))
    }
    items = json.loads(items_en_path.read_text(encoding="utf-8"))
    titles_cs = json.loads(titles_cs_path.read_text(encoding="utf-8"))

    # ---- contacts: merge Czech content + inferred OCEAN ----
    inferred_hits = 0
    without_czech: list[str] = []
    for index, contact in enumerate(contacts, start=1):
        contact["id"] = index
        rid = contact.get("reviewer_id")
        cz_reviews = reviewers_cz.get(rid, {}).get("reviews", []) if rid else []
        if cz_reviews:
            contact["frequent_words"] = _czech_frequent_words(cz_reviews) or None
            contact["prior_interactions"] = _prior_interactions(cz_reviews)
            contact["style_excerpt"] = _style_excerpt(cz_reviews)
        elif rid:
            # Reviewer exists but has no Czech translation (translation loss, see
            # amazon/translation-coverage.json): never leak the English snapshot
            # values into a Czech CRM. The cohort decision excludes these contacts.
            contact["frequent_words"] = None
            contact["prior_interactions"] = None
            contact["style_excerpt"] = None
            without_czech.append(rid)
        if rid in ocean_inferred:
            entry = ocean_inferred[rid]
            contact["ocean"] = {k: entry[k] for k in OCEAN_KEYS}
            contact["ocean_source"] = "inferred"
            inferred_hits += 1
        else:
            contact["ocean_source"] = "synthetic" if contact.get("ocean") else None

    # ---- products + asin -> product_id ----
    products: list[dict[str, Any]] = []
    asin_to_pid: dict[str, int] = {}
    for pid, item in enumerate(items, start=1):
        asin = item["asin"]
        asin_to_pid[asin] = pid
        price_usd = item.get("price")
        price_czk = round(float(price_usd) * USD_TO_CZK, 0) if price_usd not in (None, "") else None
        products.append(
            {
                "id": pid,
                "name": item.get("title") or asin,
                "category": item.get("category"),
                "price": price_czk,
                "description": item.get("description"),
                "sku": asin,
                "name_cs": titles_cs.get(asin),
            }
        )

    # ---- orders + reviews from the purchase history (one of each per source review) ----
    # The English record is the order; the same record with its Czech translation,
    # joined by (asin, timestamp), is the review. Ids are assigned here so the
    # review can point at its order before either is written.
    orders: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    translated = 0
    for contact in contacts:
        rid = contact.get("reviewer_id")
        czech_by_item = {
            (r.get("asin"), r.get("unixReviewTime")): r
            for r in reviewers_cz.get(rid, {}).get("reviews", [])
        }
        order_dates: list[date] = []
        for review in reviewers_en.get(rid, {}).get("reviews", []):
            pid = asin_to_pid.get(review.get("asin"))
            if pid is None:
                continue
            ts = review.get("unixReviewTime")
            order_date = datetime.fromtimestamp(int(ts), tz=timezone.utc).date() if ts else None
            order_id = len(orders) + 1
            orders.append(
                {
                    "id": order_id,
                    "contact_id": contact["id"],
                    "product_id": pid,
                    "quantity": 1,
                    "unit_price": products[pid - 1]["price"] or 0.0,
                    "order_date": order_date,
                }
            )
            czech = czech_by_item.get((review.get("asin"), ts), {})
            if czech:
                translated += 1
            helpful = review.get("helpful") or [0, 0]
            reviews.append(
                {
                    "id": order_id,
                    "contact_id": contact["id"],
                    "order_id": order_id,
                    "product_id": pid,
                    "rating": float(review["overall"])
                    if review.get("overall") is not None
                    else None,
                    "helpful_up": int(helpful[0]),
                    "helpful_total": int(helpful[1]),
                    "review_date": order_date,
                    "summary_en": review.get("summary") or None,
                    "text_en": review.get("reviewText") or None,
                    "summary_cs": czech.get("summary") or None,
                    "text_cs": czech.get("reviewText") or None,
                }
            )
            if order_date:
                order_dates.append(order_date)
        # Where the customer stands, from the order dates against the one "today";
        # a contact with no order is a prospect.
        contact["lifecycle_stage"] = stage_from_dates(order_dates, SUBSTRATE_REFERENCE_DATE)

    # ---- what UC-04 produced for the contacts: recommendations, topics, aspects ----
    # Loaded from UC-04's committed handoff file the way the inferred OCEAN
    # profiles are; absent or empty means UC-04 has not run, and the tables stay
    # empty rather than being invented.
    recommendations, topics, aspects = _uc04_rows(handoff_path, contacts, asin_to_pid)

    # ---- Czech notes: the committed snapshot written by substrate.generators ----
    # Pure assembly: a missing snapshot is an error, never silently replaced.
    if not notes_path.exists():
        raise FileNotFoundError(
            f"notes snapshot missing: {notes_path}. Run "
            "`python -m substrate.generators --force` first."
        )
    notes = json.loads(notes_path.read_text(encoding="utf-8"))

    # ---- companies: the committed snapshot with registry fields; every affiliation must resolve ----
    if not companies_path.exists():
        raise FileNotFoundError(
            f"companies snapshot missing: {companies_path}. Run "
            "`python -m substrate.generators --force` first."
        )
    companies = json.loads(companies_path.read_text(encoding="utf-8"))
    known_companies = {c["name"] for c in companies}
    unknown = sorted(
        {c["company_name"] for c in contacts if c.get("company_name")} - known_companies
    )
    if unknown:
        raise ValueError(f"contacts reference companies missing from the snapshot: {unknown}")

    briefs = json.loads(briefs_path.read_text(encoding="utf-8"))

    return {
        "contacts": contacts,
        "companies": companies,
        "contacts_without_czech": without_czech,
        "inferred_hits": inferred_hits,
        "products": products,
        "orders": orders,
        "reviews": reviews,
        "reviews_translated": translated,
        "recommendations": recommendations,
        "topics": topics,
        "aspects": aspects,
        "notes": notes,
        "briefs": briefs,
    }


# ---------------------------------------------------------------------------
# UC-04 results -> tables
# ---------------------------------------------------------------------------


def _uc04_rows(
    handoff_path: Path, contacts: list[dict[str, Any]], asin_to_pid: dict[str, int]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Rows for ``uc_recommendations`` / ``uc_topics`` / ``uc_aspects`` from UC-04's handoff file.

    The file is keyed by Amazon ``reviewerID``; rows are re-keyed to the contact
    that owns that reviewer today (pairing may have moved it). A reviewer no
    contact owns is skipped. Returns three empty lists when the file is absent.
    """
    if not handoff_path.exists():
        return [], [], []
    users = json.loads(handoff_path.read_text(encoding="utf-8")).get("users", {})
    contact_by_reviewer = {c["reviewer_id"]: c["id"] for c in contacts if c.get("reviewer_id")}
    recommendations: list[dict[str, Any]] = []
    topics: list[dict[str, Any]] = []
    aspects: list[dict[str, Any]] = []
    for rid, payload in users.items():
        cid = contact_by_reviewer.get(rid)
        if cid is None:
            continue
        for rank, rec in enumerate(payload.get("topk_recommendations") or [], start=1):
            recommendations.append(
                {
                    "contact_id": cid,
                    "rank": rank,
                    "product_id": asin_to_pid.get(rec.get("asin")),
                    "asin": rec.get("asin"),
                    "score": rec.get("score"),
                    "reason_cs": rec.get("reason") or None,
                    "evidence_asins": json.dumps(
                        rec.get("evidence_asin") or [], ensure_ascii=False
                    ),
                    "source": rec.get("source"),
                }
            )
        for rank, topic in enumerate(payload.get("topic_clusters") or [], start=1):
            topics.append(
                {
                    "contact_id": cid,
                    "rank": rank,
                    "label": topic.get("label") or "",
                    "weight": topic.get("weight"),
                    "evidence_titles": json.dumps(
                        topic.get("evidence_titles") or [], ensure_ascii=False
                    ),
                    "paradigm": topic.get("_paradigm"),
                }
            )
        for item in (payload.get("absa") or {}).get("aspects") or []:
            aspects.append(
                {
                    "contact_id": cid,
                    "aspect": item.get("aspect") or "",
                    "sentiment": item.get("sentiment") or "",
                    "evidence": item.get("evidence"),
                }
            )
    return recommendations, topics, aspects


# ---------------------------------------------------------------------------
# Full-text index
# ---------------------------------------------------------------------------

# External-content FTS5 index: it stores only the tokens, the text stays in
# uc_reviews (content=... , content_rowid=id). remove_diacritics 2 folds the
# Czech diacritics for matching, so "reproduktor" also finds "reproduktór".
# Match on tokens, so 'kabel*' is the prefix form that also finds "kabelu".
_FTS_CREATE = (
    f"CREATE VIRTUAL TABLE {REVIEWS_FTS_TABLE} USING fts5("
    "summary_en, text_en, summary_cs, text_cs, "
    f"content='{Review.__tablename__}', content_rowid='id', "
    "tokenize='unicode61 remove_diacritics 2')"
)
_FTS_REBUILD = f"INSERT INTO {REVIEWS_FTS_TABLE}({REVIEWS_FTS_TABLE}) VALUES('rebuild')"


# ---------------------------------------------------------------------------
# Database write
# ---------------------------------------------------------------------------


async def write_database(data: dict[str, Any], db_path: Path, *, force: bool) -> None:
    """Create the SQLite database and insert the assembled rows in foreign-key order."""
    require_can_write(db_path, overwrite=force, artifact="database")
    if db_path.exists():
        db_path.unlink()

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    contact_cols = set(Contact.model_fields.keys())
    try:
        # the lifecycle vocabulary first: contacts reference it by code
        async with session_factory() as session:
            for stage in LIFECYCLE_STAGES:
                session.add(LifecycleStage(**stage))
            await session.commit()

        # companies from the committed snapshot (registry fields included)
        company_id: dict[str, int] = {}
        async with session_factory() as session:
            for row in data["companies"]:
                session.add(Company(**{k: v for k, v in row.items() if k != "id"}))
            await session.commit()
            for company in (await session.execute(select(Company))).scalars().all():
                company_id[company.name] = company.id

        async with session_factory() as session:
            for contact in data["contacts"]:
                row = {k: v for k, v in contact.items() if k in contact_cols}
                if isinstance(row.get("date_of_birth"), str):
                    row["date_of_birth"] = date.fromisoformat(row["date_of_birth"])
                if contact.get("company_name"):
                    row["company_id"] = company_id.get(contact["company_name"])
                # Every profile, sampled or inferred, passes the schema's own
                # check on its way in: keys exactly {O,C,E,A,N}, values on the
                # 1-5 BFI scale. An out-of-scale value fails the rebuild here.
                ocean = row.pop("ocean", None)
                contact_row = Contact(**row)
                contact_row.set_ocean(ocean)
                session.add(contact_row)
            for product in data["products"]:
                session.add(Product(**{k: v for k, v in product.items() if k != "id"}))
            await session.commit()

        async with session_factory() as session:
            for order in data["orders"]:
                session.add(Order(**order))
            for brief in data["briefs"]:
                session.add(MessageBrief(**{k: v for k, v in brief.items() if k != "id"}))
            for note in data["notes"]:
                row = dict(note)
                if isinstance(row["created_at"], str):
                    row["created_at"] = datetime.fromisoformat(row["created_at"])
                session.add(Note(**row))
            await session.commit()

        # Reviews carry ~170 MB of text; a bulk INSERT keeps the step in seconds.
        # The full-text index is a virtual table SQLModel's create_all cannot
        # declare, so it is created and filled here, after the rows are in.
        async with engine.begin() as conn:
            if data["reviews"]:
                await conn.execute(insert(Review.__table__), data["reviews"])
            await conn.exec_driver_sql(_FTS_CREATE)
            await conn.exec_driver_sql(_FTS_REBUILD)
            # UC-04's per-contact results, when the handoff file is present.
            for table, rows in (
                (Recommendation.__table__, data["recommendations"]),
                (Topic.__table__, data["topics"]),
                (Aspect.__table__, data["aspects"]),
            ):
                if rows:
                    await conn.execute(insert(table), rows)
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point: assemble the snapshots and write substrate.db (build_all step ``database``)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    data = assemble()
    asyncio.run(write_database(data, Path(args.db), force=args.force))
    print(f"contacts: {len(data['contacts'])} (inferred OCEAN: {data['inferred_hits']})")
    print(
        f"  contacts without Czech reviews (fields left empty): {len(data['contacts_without_czech'])}"
    )
    print(f"companies: {len(data['companies'])}  notes: {len(data['notes'])}")
    print(f"products: {len(data['products'])}  orders: {len(data['orders'])}")
    print(
        f"reviews: {len(data['reviews'])} (with Czech text: {data['reviews_translated']}); "
        f"full-text index {REVIEWS_FTS_TABLE}"
    )
    stages = Counter(c.get("lifecycle_stage") for c in data["contacts"])
    print(f"lifecycle stages: {dict(stages)}")
    print(
        f"UC-04 results loaded: {len(data['recommendations'])} recommendations, "
        f"{len(data['topics'])} topics, {len(data['aspects'])} aspects"
    )
    print(f"briefs: {len(data['briefs'])}")
    print(f"wrote {args.db}")


if __name__ == "__main__":
    main()
