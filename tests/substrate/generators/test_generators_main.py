"""Tests for the ``contacts`` step of build_all (contacts paired with reviewers by gender inside each group, prospects unlinked).

A regression guard as well: this script once lost eleven imports in a cleanup and
could not run, while its ``--help`` smoke test kept passing.
"""

from __future__ import annotations


def _users(n: int) -> list[dict]:
    """Stratified reviewer wrappers in contiguous group blocks (A first, then B), as the chain emits them."""
    return [
        {
            "reviewerID": f"R{i}",
            "group": "A" if i < n // 2 else "B",
            "reviews": [
                {
                    "asin": f"B{i}",
                    "overall": 4.0,
                    "unixReviewTime": 100 + i,
                    "summary": f"Summary {i}",
                }
            ],
            "products": [{"asin": f"B{i}", "title": f"Product {i}"}],
        }
        for i in range(n)
    ]


def test_build_contacts_without_gender_information_is_the_positional_join():
    from substrate.generators.__main__ import build_contacts

    contacts = build_contacts(_users(6), seed=42, n_foreign=1, n_clean=5, n_non_clean=1)

    assert [c["reviewer_id"] for c in contacts] == [f"R{i}" for i in range(6)]
    assert [c["amazon_group"] for c in contacts] == ["A", "A", "A", "B", "B", "B"]
    assert all(c["reviewer_gender"] is None and c["gender_paired"] is False for c in contacts)
    assert contacts[0]["_foreign_origin"] is True
    assert contacts[-1]["is_clean"] is False


def test_pair_by_gender_matches_inside_each_group_and_keeps_group_sizes():
    """Same-gender first, unknown second, leftovers last; groups never mix."""
    from substrate.generators.__main__ import pair_by_gender

    contacts = [
        {"gender": "f"},
        {"gender": "m"},
        {"gender": "f"},  # group A block: positions 0-2
        {"gender": None},
        {"gender": "f"},  # group B block: positions 3-4
    ]
    users = [
        {"reviewerID": "A-m1", "group": "A"},
        {"reviewerID": "A-f1", "group": "A"},
        {"reviewerID": "A-m2", "group": "A"},
        {"reviewerID": "B-u1", "group": "B"},
        {"reviewerID": "B-m1", "group": "B"},
    ]
    gender = {"A-m1": "m", "A-f1": "f", "A-m2": "m", "B-u1": None, "B-m1": "m"}

    paired = [u["reviewerID"] for u in pair_by_gender(contacts, users, gender)]

    # A block: the woman at 0 takes the only female reviewer, the man at 1 a male
    # one, the woman at 2 gets the leftover male; B block: the genderless
    # contact takes the unknown reviewer, the woman the leftover male.
    assert paired == ["A-f1", "A-m1", "A-m2", "B-u1", "B-m1"]
    assert [u["group"] for u in pair_by_gender(contacts, users, gender)] == [
        "A",
        "A",
        "A",
        "B",
        "B",
    ]


def test_build_contacts_records_reviewer_gender_and_pairing():
    from substrate.generators.__main__ import build_contacts

    users = _users(6)
    plain = build_contacts(users, seed=42, n_foreign=1, n_clean=5, n_non_clean=1)
    # Give every reviewer the gender of the contact that sat opposite it, then
    # swap two reviewers of different gender inside the same group block: the
    # positional join would now mismatch both, pairing must match all again.
    gender = {f"R{i}": plain[i]["gender"] for i in range(6)}
    block_a = [i for i in range(3) if plain[i]["gender"]]
    first = block_a[0]
    other = next(i for i in block_a if plain[i]["gender"] != plain[first]["gender"])
    gender[f"R{first}"], gender[f"R{other}"] = gender[f"R{other}"], gender[f"R{first}"]

    contacts = build_contacts(
        users, seed=42, n_foreign=1, n_clean=5, n_non_clean=1, reviewer_gender=gender
    )

    linked = [c for c in contacts if c.get("gender")]
    assert all(c["reviewer_gender"] == gender[c["reviewer_id"]] for c in contacts)
    # Paired means the reviewer's gender is known AND equal; unknown never counts.
    assert all(
        c["gender_paired"] == bool(c["reviewer_gender"] and c["reviewer_gender"] == c["gender"])
        for c in contacts
    )
    assert sum(c["gender_paired"] for c in linked) == len(linked)
    assert sorted(c["reviewer_id"] for c in contacts) == [f"R{i}" for i in range(6)]


def test_build_contacts_writes_no_free_text():
    """The English review text never enters the contact snapshot; the assembler adds Czech text."""
    from substrate.generators.__main__ import build_contacts

    contacts = build_contacts(_users(6), seed=42, n_foreign=1, n_clean=5, n_non_clean=1)
    assert all(c["prior_interactions"] is None for c in contacts)
    assert all(c["frequent_words"] is None for c in contacts)
    assert all("note" not in c for c in contacts)


def test_build_contacts_is_deterministic_for_a_seed():
    from substrate.generators.__main__ import build_contacts

    a = build_contacts(_users(6), seed=42, n_foreign=1, n_clean=5, n_non_clean=1)
    b = build_contacts(_users(6), seed=42, n_foreign=1, n_clean=5, n_non_clean=1)
    assert a == b
