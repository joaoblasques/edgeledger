"""Airflow DAG: ingest_polymarket — markets, orderbook depth, and trades.

Schedule: every 15 minutes.

Polymarket is the depth venue (ADR-0002), so this DAG supplies the book data the project's
spread and CLV work depends on.

Discovery runs once per DAG run and its result is passed to the book and trade tasks, so
Gamma's 60 req/min limit is not spent rediscovering the same markets three times over.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pendulum
from airflow.decorators import dag, task

from edgeledger.config.settings import get_settings
from edgeledger.ingest import (
    ingest_polymarket_books,
    ingest_polymarket_markets,
    ingest_polymarket_trades,
)


@dag(
    dag_id="ingest_polymarket",
    schedule="*/15 * * * *",
    start_date=pendulum.datetime(2026, 8, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,  # overlapping runs would fight over the same rate limit
    tags=["ingest", "polymarket", "bronze"],
)
def ingest_polymarket():
    data_dir = Path(get_settings().edgeledger_data_dir)

    @task
    def discover_markets(**context) -> list[dict]:
        return asyncio.run(ingest_polymarket_markets(data_dir, run_id=context["run_id"]))

    @task
    def fetch_books(markets: list[dict], **context) -> int:
        return asyncio.run(ingest_polymarket_books(markets, data_dir, run_id=context["run_id"]))

    @task
    def fetch_trades(markets: list[dict], **context) -> int:
        return asyncio.run(ingest_polymarket_trades(markets, data_dir, run_id=context["run_id"]))

    markets = discover_markets()
    fetch_books(markets)
    fetch_trades(markets)


ingest_polymarket()
