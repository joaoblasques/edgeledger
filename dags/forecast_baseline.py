"""Airflow DAG: forecast_baseline. STUB with task graph, no logic — due week 3.

Schedule: 0 */6 * * * (every 6h)

For every tracked open market, run the naive baseline (forecast/baselines.py) and
append to forecast_log via forecast/log.py::append_forecast. This is the DAG that
matters — it's what starts the twelve-month clock.
"""

# from airflow.decorators import dag, task
#
# @dag(schedule="0 */6 * * *", catchup=False)
# def forecast_baseline():
#     @task
#     def list_tracked_open_markets(): ...
#     @task
#     def run_baselines_and_append(markets): ...
#
#     run_baselines_and_append(list_tracked_open_markets())
#
# forecast_baseline()
