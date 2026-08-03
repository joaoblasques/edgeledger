"""Airflow DAG: ingest_resolutions. STUB with task graph, no logic — due week 4.

Schedule: 0 6 * * * (daily, 06:00 UTC — after overnight settlements)

Polls closed markets on both venues, extracts the settled outcome, writes to
`resolutions`. Kalshi settled markets move to /historical/markets — must poll that
endpoint explicitly too, or resolutions silently vanish (see 05-Venues/Kalshi.md).
"""

# from airflow.decorators import dag, task
#
# @dag(schedule="0 6 * * *", catchup=False)
# def ingest_resolutions():
#     @task
#     def poll_kalshi_settled(): ...  # /markets (recently closed) + /historical/markets
#     @task
#     def poll_polymarket_settled(): ...
#     @task
#     def write_resolutions(kalshi_rows, poly_rows): ...
#
#     write_resolutions(poll_kalshi_settled(), poll_polymarket_settled())
#
# ingest_resolutions()
