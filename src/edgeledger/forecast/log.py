"""Append-only forecast log writer + hash chain (CLAUDE.md invariants 1, 4, 5).

Human-owned design per the automation boundary. Nothing here was invented: the hash
construction is fixed by invariant 4, the genesis constant by docs/data-model.md, and the
byte-level behaviour by tests/test_hash_chain.py. This module transcribes those.

**There is deliberately no update or delete function in this module.** Corrections are new
rows carrying `supersedes_forecast_id`. `test_hash_chain.py` asserts that no mutation API
is exported, so adding one would fail the suite — which is the point.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

from edgeledger.forecast.schema import ForecastLogRow

logger = logging.getLogger(__name__)

# The chain's anchor. Fixed in docs/data-model.md; changing it invalidates every existing
# chain, so it is a constant, never a parameter.
GENESIS_HASH = "genesis"

# Excluded from the hashed bytes: a row cannot commit to its own hash, and prev_row_hash is
# prepended separately rather than being part of the canonical body.
_HASH_EXCLUDED_FIELDS = frozenset({"row_hash", "prev_row_hash"})


def _json_default(value: Any) -> str:
    """Stable encoding for types json doesn't handle natively.

    Decimal goes to `str`, not `float`: float() would silently reround 0.55 and change the
    hash of a row that never changed. UUID and datetime use their canonical text forms.
    """
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def canonical_json(row: ForecastLogRow) -> str:
    """Deterministic JSON of the row with the hash fields excluded.

    These are the exact bytes that get hashed, so the encoding must be byte-identical
    across runs, machines, and Python versions: keys sorted, no incidental whitespace,
    and no non-ASCII escaping ambiguity.
    """
    payload = row.model_dump(mode="json", exclude=set(_HASH_EXCLUDED_FIELDS))
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=_json_default,
    )


def compute_row_hash(prev_row_hash: str, row: ForecastLogRow) -> str:
    """`sha256(prev_row_hash + canonical_json(row))` — invariant 4.

    Chaining the previous hash in is what makes the log tamper-evident: altering any row
    changes its hash, which breaks every hash after it.
    """
    return hashlib.sha256((prev_row_hash + canonical_json(row)).encode("utf-8")).hexdigest()


def verify_chain(rows: list[ForecastLogRow], *, genesis: str = GENESIS_HASH) -> None:
    """Recompute the whole chain and raise on the first inconsistency.

    This is the function an outside reviewer runs. It checks three things per row: that
    `prev_row_hash` matches the previous row's `row_hash`, that `row_hash` is what the
    contents actually hash to, and that `seq` is gapless and monotonic (invariant 5).
    """
    expected_prev = genesis
    for index, row in enumerate(rows):
        if row.seq != index:
            raise ValueError(
                f"seq gap at position {index}: expected {index}, got {row.seq} "
                "(invariant 5: a gap means a lost write)"
            )
        if row.prev_row_hash != expected_prev:
            raise ValueError(
                f"chain broken at seq {row.seq}: prev_row_hash {row.prev_row_hash!r} "
                f"does not match previous row_hash {expected_prev!r}"
            )
        recomputed = compute_row_hash(row.prev_row_hash, row)
        if row.row_hash != recomputed:
            raise ValueError(
                f"row {row.seq} has been altered: stored row_hash {row.row_hash!r} "
                f"but contents hash to {recomputed!r}"
            )
        expected_prev = row.row_hash


def _log_path(data_dir: Path) -> Path:
    """The append-only file backing the log.

    ponytail: JSON Lines, not Delta. The writer needs exactly two operations — append one
    row, read seq/hash state — and JSONL gives both with an fsync and no dependency. It is
    also trivially greppable by a reviewer verifying the chain by hand, which is the whole
    point of the artifact. Swap to Delta when partitioned reads actually hurt.
    """
    return data_dir / "forecast_log.jsonl"


def read_rows(data_dir: Path) -> list[ForecastLogRow]:
    """Read every row, in seq order. Empty list if the log does not exist yet."""
    path = _log_path(data_dir)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [ForecastLogRow.model_validate_json(line) for line in handle if line.strip()]


def head_hash(data_dir: Path) -> str:
    """The chain's current head — the hash published daily for tamper evidence."""
    rows = read_rows(data_dir)
    return rows[-1].row_hash if rows else GENESIS_HASH


def next_seq(data_dir: Path) -> int:
    """The seq the next row must carry: `max(seq) + 1`, or 0 for an empty log.

    The single place a seq is minted, and therefore the single place a gap could be
    introduced (invariant 5). Derived from what is actually on disk rather than from a
    counter, so a crashed run cannot skip a number.
    """
    rows = read_rows(data_dir)
    if not rows:
        return 0
    return max(row.seq for row in rows) + 1


def append_forecast(row: ForecastLogRow, data_dir: Path) -> ForecastLogRow:
    """Append one row. The ONLY way a row enters forecast_log (invariant 1).

    Refuses to write if `seq` is not the expected next value — a wrong seq means a
    concurrent writer or a lost read, and guessing would corrupt the chain.

    Returns the row as written, with `row_hash`/`prev_row_hash` filled in. The caller's
    instance is not mutated: rows are frozen, and a correction is a new row, never an edit.
    """
    data_dir.mkdir(parents=True, exist_ok=True)

    expected_seq = next_seq(data_dir)
    if row.seq != expected_seq:
        raise ValueError(
            f"seq {row.seq} is not the expected next seq {expected_seq} — refusing to "
            "write (invariant 5: gapless and monotonic)"
        )

    prev_hash = head_hash(data_dir)
    sealed = row.model_copy(update={"prev_row_hash": prev_hash})
    sealed = sealed.model_copy(update={"row_hash": compute_row_hash(prev_hash, sealed)})

    line = sealed.model_dump_json()
    with _log_path(data_dir).open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        # ponytail: fsync per append. These are low-frequency writes and a lost row is a
        # permanent gap in the credibility artifact, so durability beats throughput here.
        os.fsync(handle.fileno())

    logger.info(
        "forecast appended",
        extra={"seq": sealed.seq, "row_hash": sealed.row_hash, "venue": sealed.venue},
    )
    return sealed
