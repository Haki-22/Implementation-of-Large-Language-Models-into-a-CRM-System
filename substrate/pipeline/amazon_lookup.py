"""Lookup helpers for Amazon user-wrapper snapshots.

UC code should not repeatedly scan the 100+ MB `amazon-original-en.json` file.
This module exposes small, explicit functions for loading the snapshot once
and resolving a `Contact.reviewer_id` join key into the corresponding Amazon
user wrapper.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from utils.paths import REVIEWERS_EN_SNAPSHOT

DEFAULT_ENGLISH_AMAZON = REVIEWERS_EN_SNAPSHOT


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_amazon_users(path: Path | str = DEFAULT_ENGLISH_AMAZON) -> list[dict[str, Any]]:
    """Load an Amazon user-wrapper snapshot."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise TypeError(f"{path} must contain a JSON list")
    return data


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------


def index_by_reviewer(users: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return `reviewerID -> user wrapper` and reject duplicate reviewer IDs."""
    index: dict[str, dict[str, Any]] = {}
    for user in users:
        reviewer_id = user.get("reviewerID")
        if not reviewer_id:
            raise ValueError("Amazon user wrapper missing reviewerID")
        if reviewer_id in index:
            raise ValueError(f"duplicate reviewerID: {reviewer_id}")
        index[reviewer_id] = user
    return index


def get_amazon_user(
    reviewer_id: str | None,
    index: Mapping[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Resolve one reviewer ID against a prebuilt Amazon index."""
    if not reviewer_id:
        return None
    return index.get(reviewer_id)


def load_index(path: Path | str = DEFAULT_ENGLISH_AMAZON) -> dict[str, dict[str, Any]]:
    """Load an Amazon snapshot and return an indexed lookup map."""
    return index_by_reviewer(load_amazon_users(path))
