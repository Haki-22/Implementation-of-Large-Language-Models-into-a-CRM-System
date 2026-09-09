"""The intrinsic metrics (metrics.py), without a database or a model."""

from __future__ import annotations

from ucs.uc01_personalization.metrics import flip_ocean, lsm_index, overlap_rate


def test_lsm_is_one_for_identical_texts_and_lower_for_different_function_word_use():
    a = "Já jsem ho koupil a je to velmi dobré, ale ne pro každého."
    assert lsm_index(a, a) == 1.0
    b = "Kabel. Zvuk. Cena. Doprava."
    assert lsm_index(a, b) < lsm_index(a, a)
    assert 0.0 <= lsm_index(a, b) <= 1.0


def test_overlap_rate_counts_verbatim_reuse_only():
    assert overlap_rate("Skvělý kabel a čistý zvuk.", ["kabel", "zvuk", "baterie"]) == 2 / 3
    assert overlap_rate("Skvělý kabel.", []) is None


def test_flip_ocean_mirrors_across_the_midpoint():
    assert flip_ocean({"O": 4.6, "C": 1.0, "E": 3.0, "A": 2.5, "N": 5.0, "junk": 1}) == {
        "O": 1.4,
        "C": 5.0,
        "E": 3.0,
        "A": 3.5,
        "N": 1.0,
    }
