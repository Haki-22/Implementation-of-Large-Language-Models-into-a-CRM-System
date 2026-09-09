"""UC-04 sample: the fixed customer sample of the model arms is a rule, deterministic, pick first.

A toy substrate with three groups is enough to pin what the rule must never get
wrong: the pick's linked contacts of a group come first, the rest is a seeded draw
that repeats exactly, prospects and one-review customers are never sampled, a
quota larger than the group is an error, and the file round-trips.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ucs.uc04_matchmaker import sample as sampling

# (contact, reviewer, group, number of reviews)
CONTACTS = [
    (1, "R1", "A", 3),
    (2, "R2", "A", 2),
    (3, "R3", "A", 4),
    (4, "R4", "A", 2),
    (5, "R5", "B", 3),
    (6, "R6", "B", 2),
    (7, "R7", "C", 2),
    (8, "R8", "C", 5),
    (9, "R9", "C", 1),  # one review only: not in the arena
]


@pytest.fixture()
def toy_db(tmp_path: Path) -> Path:
    """A three-group SQLite file (``CONTACTS``), with one prospect and one one-review contact."""
    path = tmp_path / "substrate.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE uc_contacts (id INTEGER PRIMARY KEY, reviewer_id TEXT, amazon_group TEXT, ocean_source TEXT);
        CREATE TABLE uc_products (id INTEGER PRIMARY KEY, sku TEXT, name TEXT, name_cs TEXT, category TEXT, description TEXT, price REAL);
        CREATE TABLE uc_reviews (id INTEGER PRIMARY KEY, contact_id INTEGER, product_id INTEGER, rating REAL,
                                 review_date TEXT, summary_en TEXT, text_en TEXT, summary_cs TEXT, text_cs TEXT);
        """
    )
    for pid in range(1, 7):
        conn.execute(
            "INSERT INTO uc_products VALUES (?,?,?,?,?,?,?)",
            (pid, f"P{pid}", f"Product {pid}", None, "Cat", "", 1.0),
        )
    conn.execute("INSERT INTO uc_contacts VALUES (99, NULL, NULL, NULL)")  # a prospect
    rid = 0
    for cid, reviewer, group, n_reviews in CONTACTS:
        conn.execute(
            "INSERT INTO uc_contacts VALUES (?,?,?,?)",
            (cid, reviewer, group, "inferred" if cid == 1 else "synthetic"),
        )
        for k in range(n_reviews):
            rid += 1
            conn.execute(
                "INSERT INTO uc_reviews VALUES (?,?,?,?,?,?,?,?,?)",
                (rid, cid, k + 1, 4.0, f"2013-0{k + 1}-01", "s", "t", "s", "t"),
            )
    conn.commit()
    conn.close()
    return path


def _conn(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


PICK = {
    "name": "toy-pick",
    "contacts": {
        "3": {"tier": "full", "amazon_group": "A"},
        "6": {"tier": "partial", "amazon_group": "B"},
        "99": {"tier": "prospect", "amazon_group": None},
    },
}
QUOTAS = {"A": 2, "B": 1, "C": 1}


def test_pick_members_come_first_and_prospects_are_ignored(toy_db: Path) -> None:
    built = sampling.build_sample(
        _conn(toy_db), pick=PICK, pick_name="toy-pick", quotas=QUOTAS, seed=1
    )
    assert 3 in built["groups"]["A"] and built["groups"]["B"] == [6]
    assert built["pick"]["members_per_group"] == {"A": 1, "B": 1, "C": 0}
    assert built["contacts"]["3"]["pick_tier"] == "full"
    assert built["contacts"]["6"]["pick_tier"] == "partial"
    assert 99 not in built["contact_ids"] and 9 not in built["contact_ids"]
    assert built["contact_ids"] == sorted(built["contact_ids"])
    assert built["reviewer_ids"] == [f"R{c}" for c in built["contact_ids"]]
    assert (
        built["contacts"]["1"]["ocean_source"] == "inferred" if "1" in built["contacts"] else True
    )
    assert built["contacts"]["3"]["reviews"] == 4


def test_the_draw_is_deterministic_for_a_seed(toy_db: Path) -> None:
    first = sampling.build_sample(_conn(toy_db), pick=None, pick_name=None, quotas=QUOTAS, seed=7)
    again = sampling.build_sample(_conn(toy_db), pick=None, pick_name=None, quotas=QUOTAS, seed=7)
    assert first["groups"] == again["groups"]
    assert first["pick"]["members_per_group"] == {"A": 0, "B": 0, "C": 0}
    assert all(len(ids) == QUOTAS[g] for g, ids in first["groups"].items())
    assert first["arena"] == {"linked_customers": 8, "per_group": {"A": 4, "B": 2, "C": 2}}


def test_a_quota_above_the_group_is_an_error(toy_db: Path) -> None:
    with pytest.raises(LookupError, match="group C"):
        sampling.build_sample(
            _conn(toy_db), pick=None, pick_name=None, quotas={"A": 1, "B": 1, "C": 3}, seed=1
        )
    with pytest.raises(LookupError, match="pick members"):
        sampling.build_sample(
            _conn(toy_db),
            pick={
                "name": "p",
                "contacts": {
                    "1": {"tier": "full", "amazon_group": "A"},
                    "2": {"tier": "full", "amazon_group": "A"},
                },
            },
            pick_name="p",
            quotas={"A": 1, "B": 1, "C": 1},
            seed=1,
        )


def test_the_file_round_trips_and_refuses_to_overwrite(toy_db: Path, tmp_path: Path) -> None:
    built = sampling.build_sample(
        _conn(toy_db), pick=PICK, pick_name="toy-pick", name="toy", quotas=QUOTAS, seed=1
    )
    base = tmp_path / "samples"
    path = sampling.write_sample(built, base=base)
    assert path == base / "toy.json"
    assert sampling.load_sample("toy", base=base)["contact_ids"] == built["contact_ids"]
    with pytest.raises(FileExistsError):
        sampling.write_sample(built, base=base)
    sampling.write_sample(built, base=base, overwrite=True)
    with pytest.raises(FileNotFoundError, match="uc04_matchmaker sample"):
        sampling.load_sample("missing", base=base)
