"""Airflow DAG: ingest_kalshi — markets and trades.

Schedule: every 15 minutes.

Unauthenticated endpoints only. There is deliberately no orderbook task: Kalshi's depth
endpoint needs an account this project cannot obtain, and Polymarket supplies depth
instead (ADR-0002). If that ever changes, a `fetch_orderbooks` task slots in here — the
client method and its signing requirement are already mapped in `clients/kalshi.py`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pendulum
from airflow.decorators import dag, task

from edgeledger.config.settings import get_settings
from edgeledger.ingest import ingest_kalshi_markets, ingest_kalshi_trades


@dag(
    dag_id="ingest_kalshi",
    schedule="*/15 * * * *",
    start_date=pendulum.datetime(2026, 8, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    tags=["ingest", "kalshi", "bronze"],
)
def ingest_kalshi():
    data_dir = Path(get_settings().edgeledger_data_dir)

    @task
    def discover_markets(**context) -> int:
        markets = asyncio.run(ingest_kalshi_markets(data_dir, run_id=context["run_id"]))
        return len(markets)

    @task
    def fetch_trades(**context) -> int:
        return asyncio.run(ingest_kalshi_trades(data_dir, run_id=context["run_id"]))

    discover_markets() >> fetch_trades()


ingest_kalshi()
