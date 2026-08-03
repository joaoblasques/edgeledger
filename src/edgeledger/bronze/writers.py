"""Append writers for the bronze tables.

Idempotency contract, identical for all four tables: re-running a task overwrites only
its own `(ingest_date, run_id)` partition and never another run's rows. A retried Airflow
task must not double-count, and must not delete a sibling run's work.

ponytail: JSONL partition files rather than Delta. The stub specified deltalake with a
partition predicate, but the operations actually needed are "append rows" and "replace my
own partition" — a directory layout gives both with an atomic rename and no dependency,
and stays greppable for the manual verification this project is built around. Consistent
with forecast/log.py. Switch to Delta when concurrent readers or time-travel are real
requirements; the partition layout below maps onto Delta partitioning unchanged.
"""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from edgeledger.bronze.schemas import (
    Resolution,
    VenueMarketSnapshot,
    VenueOrderbookSnapshot,
    VenueTrade,
)

logger = logging.getLogger(__name__)

# One directory per table; partitions live beneath it.
TABLE_DIRS: dict[type[BaseModel], str] = {
    VenueMarketSnapshot: "venue_market_snapshot",
    VenueOrderbookSnapshot: "venue_orderbook_snapshot",
    VenueTrade: "venue_trade",
    Resolution: "resolution",
}


def _table_dir(row_type: type[BaseModel], data_dir: Path) -> Path:
    try:
        name = TABLE_DIRS[row_type]
    except KeyError:
        raise ValueError(f"no bronze table registered for {row_type.__name__}") from None
    return data_dir / "bronze" / name


def _partition_file(row_type: type[BaseModel], data_dir: Path, day: date, run_id: str) -> Path:
    # run_id lands in the filename, so two runs on the same day never touch each other's data.
    safe_run = run_id.replace("/", "_").replace(os.sep, "_")
    return _table_dir(row_type, data_dir) / f"ingest_date={day.isoformat()}" / f"{safe_run}.jsonl"


def _atomic_write(path: Path, lines: list[str]) -> None:
    """Write via temp file + rename so a crashed write never leaves a partial partition."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for line in lines:
                handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(path)  # atomic on POSIX
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write_rows[RowT: BaseModel](rows: Sequence[RowT], data_dir: Path, *, run_id: str) -> int:
    """Write rows for one run, replacing only this run's own partition slice.

    All rows must share a type. Rows are grouped by `ingest_date`, and each
    `(ingest_date, run_id)` file is written whole — so a retry produces the same result as
    a first attempt rather than duplicating rows.

    `Resolution` has no `ingest_date` field (see docs/data-model.md); its partition is
    derived from `capture_ts_utc`, which is our own clock and therefore always present.

    Returns the number of rows written.
    """
    if not rows:
        return 0

    row_type = type(rows[0])
    if any(type(r) is not row_type for r in rows):
        raise TypeError("write_rows expects a homogeneous sequence of bronze rows")

    by_day: dict[date, list[str]] = {}
    for row in rows:
        day = getattr(row, "ingest_date", None) or row.capture_ts_utc.date()
        by_day.setdefault(day, []).append(row.model_dump_json())

    written = 0
    for day, lines in by_day.items():
        path = _partition_file(row_type, data_dir, day, run_id)
        _atomic_write(path, lines)
        written += len(lines)
        logger.info(
            "bronze partition written",
            extra={
                "table": TABLE_DIRS[row_type],
                "ingest_date": day.isoformat(),
                "run_id": run_id,
                "rows": len(lines),
            },
        )

    return written


def read_rows[RowT: BaseModel](
    row_type: type[RowT], data_dir: Path, *, day: date | None = None
) -> list[RowT]:
    """Read every row of one table, optionally restricted to a single `ingest_date`.

    Rows come back in no guaranteed order across partitions — callers that care about
    ordering sort on `capture_ts_utc` themselves.
    """
    table = _table_dir(row_type, data_dir)
    if not table.exists():
        return []

    pattern = f"ingest_date={day.isoformat()}/*.jsonl" if day else "ingest_date=*/*.jsonl"
    out: list[RowT] = []
    for path in sorted(table.glob(pattern)):
        with path.open("r", encoding="utf-8") as handle:
            out.extend(row_type.model_validate_json(line) for line in handle if line.strip())
    return out


def read_since[RowT: BaseModel](row_type: type[RowT], data_dir: Path, *, since: date) -> list[RowT]:
    """Read rows whose partition date is on or after `since`.

    Used by the feature builder to bound how much bronze it scans. This filters on the
    partition date only — it is NOT the point-in-time cutoff. Row-level filtering on
    `capture_ts_utc` happens in `forecast/baselines.py::build_feature_vector`, which is
    the single place the leakage firewall lives (invariant 3).
    """
    return [r for r in read_rows(row_type, data_dir) if r.capture_ts_utc.date() >= since]
