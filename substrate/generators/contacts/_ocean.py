"""OCEAN trait sampling.

Truncated normal on the 1-5 BFI raw scale, BFI-2 representative-sample norms
(Soto & John 2017). Independent draws (Big Five are near-orthogonal).

``_make_ocean_from_latent(seniority, warmth, rng)`` follows the CRMArena
causal-DGP pattern: two latent variables shift per-trait means by up to
+-0.15 (the latent half-shift of 0.3 multiplied by ``x - 0.5`` for centring).
"""

from __future__ import annotations

import random

from ._constants import _OCEAN_HIGH, _OCEAN_LOW, _OCEAN_NORMS


# ---------------------------------------------------------------------------
# Trait sampling
# ---------------------------------------------------------------------------


def _sample_trait(mu: float, sigma: float, rng: random.Random) -> float:
    """
    Sample one OCEAN trait from a truncated normal on the 1-5 BFI scale.

    Uses stdlib sample-and-clip (scipy not required).
    Truncation bounds are >= 2.7 sigma from every mean, so clipping affects
    < ~0.4% of draws and does not visibly distort the distribution.
    """
    return round(min(_OCEAN_HIGH, max(_OCEAN_LOW, rng.gauss(mu, sigma))), 2)


# ---------------------------------------------------------------------------
# Latent modulation
# ---------------------------------------------------------------------------


def _make_ocean_from_latent(
    purchase_seniority: float, relationship_warmth: float, rng: random.Random
) -> dict[str, float]:
    """
    CRMArena causal-DGP pattern: latent variables partially modulate the
    per-trait OCEAN means.

    purchase_seniority -> C up, O up   (long-standing customers are more
                                        conscientious/open in their buying behaviour)
    relationship_warmth -> A up, E up  (warm contacts are agreeable/extraverted)
    N is near-base (not causally determined by these latents at this scale).

    Latent shift is +-0.15 at most (0.3 x (latent - 0.5)), keeping values within
    the realistic BFI range.
    All values clipped to [OCEAN_LOW=1.0, OCEAN_HIGH=5.0] and rounded to 2dp.
    """
    latent_shift = 0.3  # maximum half-shift per latent unit

    modulated_means = {
        "O": _OCEAN_NORMS["O"][0] + latent_shift * (purchase_seniority - 0.5),
        "C": _OCEAN_NORMS["C"][0] + latent_shift * (purchase_seniority - 0.5),
        "E": _OCEAN_NORMS["E"][0] + latent_shift * (relationship_warmth - 0.5),
        "A": _OCEAN_NORMS["A"][0] + latent_shift * (relationship_warmth - 0.5),
        "N": _OCEAN_NORMS["N"][0],  # no latent modulation
    }

    return {
        trait: _sample_trait(modulated_means[trait], _OCEAN_NORMS[trait][1], rng)
        for trait in _OCEAN_NORMS
    }
