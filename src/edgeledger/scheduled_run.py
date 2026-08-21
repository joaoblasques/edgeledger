"""One scheduled cycle: ingest → forecast → archive → report.

This is what the GitHub Actions workflow invokes. It exists as a module rather than
inline shell so the whole cycle is testable and so the ordering guarantees below are
enforced in one place rather than spread across YAML.

Ordering is deliberate and load-bearing:

  1. **Ingest first.** Market state must be captured before anything forecasts on it.
     Settled outcomes are polled in the same step: they feed the scoring view, never the
     forecast, so they cannot influence what is predicted.
  2. **Forecast second**, from what was just captured — never from a later fetch, which
     would break invariant 2.
  3. **Archive last.** Bronze upload is best-effort and must never be able to prevent a
     forecast from being written (see `archive.py`).
  4. **Verify the chain** before reporting success, so a corrupt log fails the run loudly
     instead of being silently committed.

Exit codes: 1 when the forecast log itself is broken, 2 when a pipeline step silently
stopped running (see `check_wiring`). A venue outage or a failed archive is reported but
does not fail the run: the schedule must keep its cadence, and a run that writes zero
forecasts because Polymarket was down is a true observation, not an error.

A non-zero exit is how this reports to a human — GitHub emails the owner on a failed run,
so the alerting path is the CI platform's, with nothing extra to configure or to break.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

from edgeledger.archive import archive_bronze
from edgeledger.forecast.log import head_hash, read_rows, verify_chain
from edgeledger.forecast.runner import run_market_mirror
from edgeledger.ingest import (
    ingest_polymarket_books,
    ingest_polymarket_markets,
    ingest_polymarket_resolutions_for_forecast_markets,
)

logger = logging.getLogger(__name__)


async def _ingest(data_dir: Path, run_id: str, market_pages: int, book_limit: int) -> dict:
    """Fetch market state and depth. A venue failure degrades the run, never fails it."""
    result = {"markets": 0, "books": 0, "resolutions": 0, "ingest_error": None}
    try:
        markets = await ingest_polymarket_markets(data_dir, run_id=run_id, max_pages=market_pages)
        result["markets"] = len(markets)
        result["books"] = await ingest_polymarket_books(
            markets, data_dir, run_id=run_id, limit=book_limit
        )
        # Resolutions are what make every logged forecast eventually scoreable. Looked up
        # by the ids in the forecast log, NOT by scanning the closed feed — that feed is
        # ordered oldest-first, so a bounded scan never reaches the markets we forecast.
        result["resolutions"] = await ingest_polymarket_resolutions_for_forecast_markets(
            data_dir, run_id=run_id
        )
    except (httpx.HTTPStatusError, httpx.RequestError, OSError) as exc:
        # No forecasts this cycle, but the schedule holds and the next run recovers.
        result["ingest_error"] = f"{type(exc).__name__}: {exc}"
        logger.warning("ingestion failed; continuing to forecast on whatever exists")
    return result


def run_cycle(
    data_dir: Path,
    *,
    run_id: str | None = None,
    market_pages: int = 4,
    book_limit: int = 25,
    archive: bool = True,
) -> dict:
    """Run one full cycle and return a summary dict.

    Raises only if the forecast log fails verification — that is the one condition where
    continuing would publish an untrustworthy artifact.
    """
    started = datetime.now(UTC)
    run_id = run_id or f"scheduled__{started.strftime('%Y%m%dT%H%M%SZ')}"

    summary: dict = {"run_id": run_id, "started_utc": started.isoformat()}
    summary.update(asyncio.run(_ingest(data_dir, run_id, market_pages, book_limit)))

    summary["forecasts"] = run_market_mirror(data_dir, run_id=run_id)

    if archive:
        uploaded, failed = archive_bronze(data_dir)
        summary["archived"] = uploaded
        summary["archive_failed"] = failed

    # The gate: a chain that does not verify must never be reported as a good run.
    rows = read_rows(data_dir)
    verify_chain(rows)
    summary["log_rows"] = len(rows)
    summary["head_hash"] = head_hash(data_dir)
    summary["finished_utc"] = datetime.now(UTC).isoformat()

    return summary


class WiringError(RuntimeError):
    """A step that should have run did not. Distinct from a venue being down."""


def check_wiring(summary: dict) -> None:
    """Fail the run when a pipeline step silently stopped being called.

    The bug this exists to catch: resolutions were implemented but never invoked by the
    scheduled cycle, so every forecast was permanently unscoreable — and nothing anywhere
    reported a problem, because a cycle that writes forecasts and verifies its chain looks
    completely healthy. Silence was the failure mode.

    What is checked is that the *key is present*, never that it is non-zero. Zero
    resolutions is the honest and expected answer while every tracked market is still
    open; treating it as an error would train the alert to be ignored, which is how a real
    break gets missed. A missing key means the code path did not run at all.

    Skipped when ingestion failed: a venue outage is a true observation and must not be
    reported as a wiring bug (see the module docstring).
    """
    if summary.get("ingest_error"):
        return
    missing = [k for k in ("markets", "books", "resolutions", "forecasts") if k not in summary]
    if missing:
        raise WiringError(
            f"cycle summary is missing {missing} — a pipeline step did not run. "
            "Every logged forecast stays unscoreable until this is fixed."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one scheduled EdgeLedger cycle.")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--market-pages", type=int, default=4)
    parser.add_argument("--book-limit", type=int, default=25)
    parser.add_argument("--no-archive", action="store_true", help="skip the R2 upload")
    parser.add_argument("--summary-out", type=Path, help="write the JSON summary here")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    try:
        summary = run_cycle(
            args.data_dir,
            market_pages=args.market_pages,
            book_limit=args.book_limit,
            archive=not args.no_archive,
        )
    except ValueError as exc:
        # verify_chain raises ValueError — the log is corrupt. This must fail the run.
        logger.error("FORECAST LOG VERIFICATION FAILED: %s", exc)
        return 1

    text = json.dumps(summary, indent=2, sort_keys=True)
    print(text)
    # Written before the wiring check so a failing run still leaves its summary behind to
    # inspect — the diagnostic must survive the failure it is diagnosing.
    if args.summary_out:
        args.summary_out.write_text(text + "\n", encoding="utf-8")

    try:
        check_wiring(summary)
    except WiringError as exc:
        logger.error("PIPELINE WIRING CHECK FAILED: %s", exc)
        return 2

    if summary.get("ingest_error"):
        logger.warning("cycle completed with a degraded ingest: %s", summary["ingest_error"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
