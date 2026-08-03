"""Delta append writers for bronze tables. STUB — due week 1-2.

Intended shape:

    def write_snapshot(rows: list[VenueMarketSnapshot], data_dir: Path) -> None:
        '''Append-only write, partitioned by ingest_date + run_id. Idempotent: re-running
        a task overwrites only its own (ingest_date, run_id) partition, never another
        run's rows. Uses deltalake's `mode="overwrite"` with a partition predicate, not
        a blanket overwrite.'''

Applies to all four bronze tables (snapshot, orderbook, trade, resolution) — same
idempotency contract each time.
"""
