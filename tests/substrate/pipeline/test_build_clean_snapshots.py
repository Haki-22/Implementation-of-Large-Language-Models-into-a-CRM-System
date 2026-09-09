"""Unit tests for the pure helpers of build_clean_snapshots (catalog repair, coverage)."""

from __future__ import annotations


def test_catalog_entry_repairs_mojibake_entities_and_html():
    from substrate.pipeline.build_clean_snapshots import catalog_entry

    # Title exactly as the raw Amazon meta dump ships it (asin B000DZGA92): entities, C1 byte lost.
    # file stays free of invisible / mojibake characters.
    mojibake_title = "Jensen WBT212 Universal Bluetooth&Atilde;&cent;&Acirc;&Acirc;&cent; Stereo Headphones"
    entry = catalog_entry(
        "B1",
        mojibake_title,
        {"category": "Headphones", "price": 9.5,
         "description": "<p>1GHz &amp;amp; 512MB</p><script>x()</script> slot \u00e2\u20ac\u201c none\ufffd"},
    )
    assert entry == {"asin": "B1", "title": "Jensen WBT212 Universal Bluetooth\u2122 Stereo Headphones",
                     "category": "Headphones", "price": 9.5, "description": "1GHz & 512MB slot \u2013 none"}



def test_catalog_entry_falls_back_to_asin_title():
    from substrate.pipeline.build_clean_snapshots import catalog_entry

    assert catalog_entry("B2", None, {})["title"] == "B2"


def test_coverage_rows_sorted_by_loss():
    from substrate.pipeline.build_clean_snapshots import coverage

    en = [{"reviewerID": "U1", "group": "A", "reviews": [1, 2, 3, 4]},
          {"reviewerID": "U2", "group": "B", "reviews": [1, 2]}]
    cz = [{"reviewerID": "U1", "group": "A", "reviews": [1]},
          {"reviewerID": "U2", "group": "B", "reviews": [1, 2]}]
    rows = coverage(en, cz)
    assert rows == [
        {"reviewerID": "U1", "group": "A", "en_reviews": 4, "cz_reviews": 1, "lost": 3, "loss_ratio": 0.75},
        {"reviewerID": "U2", "group": "B", "en_reviews": 2, "cz_reviews": 2, "lost": 0, "loss_ratio": 0.0},
    ]
