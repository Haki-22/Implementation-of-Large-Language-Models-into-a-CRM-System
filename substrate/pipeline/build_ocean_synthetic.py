"""Project the OCEAN synthetic snapshot from the English-mapped contacts.

Pure projection — no RNG, no LLM, no model dispatch. Each row is read straight
off the contacts snapshot. The generator gives an OCEAN vector to about 70 % of
contacts on purpose (missing-data realism); ``source`` is ``synth-bfi2-norms``
for those and ``none-by-design`` for contacts whose vector is ``null``.

Inputs
------
- ``contacts/contacts.json``

Output
------
- ``ocean/ocean_synthetic_500.json``

Run:
    python -m substrate.pipeline.build_ocean_synthetic
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from utils.paths import CONTACTS_SNAPSHOT, SNAPSHOTS_DIR

OUT_PATH = SNAPSHOTS_DIR / "ocean" / "ocean_synthetic_500.json"

_SCHEMA = {"version": "1.0", "kind": "ocean_synthetic_full"}
_SOURCE_DESCRIPTION = (
    "BFI-2 population norms (Soto & John 2017) with CRMArena DGP modulation (±0.15 effective shift)"
)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point: project the sampled OCEAN vectors out of the contacts snapshot."""
    parser = argparse.ArgumentParser(
        description=(
            "Re-derive substrate/snapshots/ocean/ocean_synthetic_500.json from "
            "the contacts snapshots. Pure projection; byte-identical to the "
            "committed file."
        )
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=OUT_PATH,
        help=f"Output path (default: {OUT_PATH}).",
    )
    args = parser.parse_args()
    out_path: Path = args.out

    contacts = json.loads(CONTACTS_SNAPSHOT.read_text(encoding="utf-8"))

    # Every contact, not only the ones with an Amazon link: this records what the
    # generator sampled, and it samples OCEAN for prospects too. Keyed by contact
    # position, with the reviewer id carried when there is one.
    rows = []
    for index, contact in enumerate(contacts, start=1):
        source = "synth-bfi2-norms" if contact.get("ocean") else "none-by-design"
        rows.append(
            {
                "contact_id": index,
                "reviewer_id": contact.get("reviewer_id"),
                "amazon_group": contact.get("amazon_group"),
                "ocean": contact.get("ocean"),
                "source": source,
            }
        )

    payload = {
        "_schema": _SCHEMA,
        "source": _SOURCE_DESCRIPTION,
        "total": len(rows),
        "with_ocean": sum(1 for r in rows if r["ocean"]),
        "rows": rows,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {out_path.name}: {len(rows)} rows, {payload['with_ocean']} with an OCEAN vector")


if __name__ == "__main__":
    main()
