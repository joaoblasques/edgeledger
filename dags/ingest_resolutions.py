"""Airflow DAG: ingest_resolutions — settled outcomes from both venues.

Schedule: daily at 06:00 UTC, after overnight settlements.

Kalshi settled markets vanish from `/markets` and move to `/historical/markets`, so both
are polled — polling only the former loses resolutions silently, and a resolution that
never arrives means a forecast that never gets scored.

A market whose outcome cannot be determined is skipped, not guessed. Polymarket reports
some closed markets with no usable price information, and writing a fabricated outcome
into the scoring path would be far worse than waiting for the next daily run.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pendulum
from airflow.decorators import dag, task

from edgeledger.config.settings import get_settings
from edgeledger.ingest import ingest_kalshi_resolutions, ingest_polymarket_resolutions


@dag(
    dag_id="ingest_resolutions",
    schedule="0 6 * * *",
    start_date=pendulum.datetime(2026, 8, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    tags=["ingest", "resolutions", "bronze"],
)
def ingest_resolutions():
    data_dir = Path(get_settings().edgeledger_data_dir)

    @task
    def poll_kalshi_settled(**context) -> int:
        return asyncio.run(ingest_kalshi_resolutions(data_dir, run_id=context["run_id"]))

    @task
    def poll_polymarket_settled(**context) -> int:
        return asyncio.run(ingest_polymarket_resolutions(data_dir, run_id=context["run_id"]))

    # Independent: one venue failing must not block the other's resolutions.
    poll_kalshi_settled()
    poll_polymarket_settled()


ingest_resolutions()
