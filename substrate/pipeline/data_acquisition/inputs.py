"""Are the raw inputs on disk, and fetch them if not.

One module knows every pinned download the substrate is built from -- the two
Amazon dumps (``fetch_and_filter.SOURCES``) and the ČSÚ + Czech Post files
(``fetch_csu.SOURCES``) -- so the chain, a reader's first run and the demo
frontend ask the same two questions through the same code:

- ``raw_status()``: per group and file, ``ok`` | ``missing`` | ``size-mismatch``
  | ``md5-mismatch`` against the pins;
- ``ensure_raw_inputs()``: fetch what is *missing*, verify, return the status.

A file that exists but does not match its pin is never overwritten silently:
that is either a truncated transfer or an upstream change, and both deserve a
human look, so the function raises and names the file. Downloads land under
``data_acquisition/downloaded/`` and are verified against size + md5, so a rebuild
either runs on exactly the published data or stops.
"""

from __future__ import annotations

from pathlib import Path

from substrate.pipeline.data_acquisition import _pinned, fetch_and_filter, fetch_csu

# group -> (pinned sources, directory they live in)
RAW_INPUTS: dict[str, tuple[dict, Path]] = {
    "amazon": (fetch_and_filter.SOURCES, fetch_and_filter.DATA_DIR),
    "csu": (fetch_csu.SOURCES, fetch_csu.RAW_DIR),
}

Inputs = dict[str, tuple[dict, Path]]
Status = dict[str, dict[str, str]]


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def raw_status(inputs: Inputs | None = None) -> Status:
    """Per group, per file: ``ok`` | ``missing`` | ``size-mismatch`` | ``md5-mismatch``."""
    inputs = RAW_INPUTS if inputs is None else inputs
    return {group: _pinned.verify(sources, raw_dir) for group, (sources, raw_dir) in inputs.items()}


def problems(status: Status) -> list[str]:
    """Flat ``group/file: state`` lines for everything that is not ``ok``."""
    return [
        f"{group}/{name}: {state}"
        for group, files in status.items()
        for name, state in files.items()
        if state != "ok"
    ]


def download_size_mb(inputs: Inputs | None = None, status: Status | None = None) -> float:
    """How many MB ``ensure_raw_inputs`` would fetch right now."""
    inputs = RAW_INPUTS if inputs is None else inputs
    status = raw_status(inputs) if status is None else status
    return sum(
        spec["size"] / 1e6
        for group, (sources, _) in inputs.items()
        for name, spec in sources.items()
        if status[group].get(name) == "missing"
    )


# ---------------------------------------------------------------------------
# Ensure
# ---------------------------------------------------------------------------


def ensure_raw_inputs(
    *, download: bool = True, inputs: Inputs | None = None, announce: bool = True
) -> Status:
    """Return the verified status, fetching missing files first when ``download`` is on.

    Raises:
        FileNotFoundError: something is missing or mismatched and ``download`` is off.
        RuntimeError: a file exists but does not match its pin (never overwritten), or
            a download did not verify afterwards.
    """
    inputs = RAW_INPUTS if inputs is None else inputs
    status = raw_status(inputs)
    if not problems(status):
        return status
    if not download:
        raise FileNotFoundError(
            "raw inputs missing or not matching their pins:\n  "
            + "\n  ".join(problems(status))
            + "\nRun `python -m substrate.pipeline.build_all --force` (fetches what is missing) "
            "or the fetchers' `--download` form."
        )
    mismatched = [line for line in problems(status) if not line.endswith(": missing")]
    if mismatched:
        raise RuntimeError(
            "raw inputs on disk do not match their pins (truncated transfer or upstream change); "
            "delete them and re-run to fetch afresh:\n  " + "\n  ".join(mismatched)
        )
    for group, (sources, raw_dir) in inputs.items():
        missing = {name: spec for name, spec in sources.items() if status[group][name] == "missing"}
        if not missing:
            continue
        if announce:
            total = sum(spec["size"] for spec in missing.values()) / 1e6
            print(
                f"[{group}] fetching {len(missing)} missing raw input(s), {total:.0f} MB, into {raw_dir}",
                flush=True,
            )
        _pinned.download(missing, raw_dir, announce=announce)
        status[group] = _pinned.verify(sources, raw_dir)
    if problems(status):
        raise RuntimeError(
            "raw inputs still not matching their pins after download:\n  "
            + "\n  ".join(problems(status))
        )
    return status
