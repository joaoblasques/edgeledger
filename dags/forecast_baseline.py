"""Airflow DAG: forecast_baseline — the DAG that starts the twelve-month clock.

Schedule: every 6 hours.

Runs the naive baseline over every tracked market and appends each forecast to
`forecast_log`. Once this DAG has run in production, its output is permanent: the log is
append-only, so a bad forecast is corrected by a new superseding row, never by an edit.

`max_active_runs=1` is a correctness requirement, not tuning. `seq` must be gapless and
monotonic (invariant 5), and two concurrent runs minting seqs from the same log would
race. The writer refuses a seq that is not the expected next one, so a race fails loudly
rather than corrupting the chain — but it should not be able to happen at all.
"""

from __future__ import annotations

from pathlib import Path

import pendulum
from airflow.decorators import dag, task

from edgeledger.config.settings import get_settings
from edgeledger.forecast.runner import run_market_mirror


@dag(
    dag_id="forecast_baseline",
    schedule="0 */6 * * *",
    start_date=pendulum.datetime(2026, 8, 1, tz="UTC"),
    catchup=False,  # a backfilled forecast would be a forecast made after the fact
    max_active_runs=1,  # invariant 5: one writer, or seq can race
    tags=["forecast", "baseline"],
)
def forecast_baseline():
    data_dir = Path(get_settings().edgeledger_data_dir)

    @task
    def run_baselines_and_append(**context) -> int:
        return run_market_mirror(data_dir, run_id=context["run_id"])

    run_baselines_and_append()


forecast_baseline()
