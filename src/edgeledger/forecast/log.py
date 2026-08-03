"""Append-only forecast log writer + hash chain. STUB — due week 3. Human-owned design
(CLAUDE.md automation boundary) — an agent should not decide this file's logic
unsupervised.

Intended shape:

    def canonical_json(row: ForecastLogRow) -> str:
        '''Deterministic JSON of the row with row_hash/prev_row_hash excluded — the
        exact bytes that get hashed. Field order and separators must be stable across
        runs (json.dumps(..., sort_keys=True, separators=(",", ":"))).'''

    def compute_row_hash(prev_row_hash: str, row: ForecastLogRow) -> str:
        '''sha256(prev_row_hash + canonical_json(row)) — CLAUDE.md invariant 4.'''

    def next_seq(data_dir: Path) -> int:
        '''Read current max(seq) from the Delta table + 1. Gaps are lost writes and
        must be monitored (invariant 5) — this function is the single place a seq is
        minted, so it is also the single place a gap could be introduced.'''

    def append_forecast(row: ForecastLogRow, data_dir: Path) -> None:
        '''The ONLY way a row enters forecast_log. No UPDATE, no DELETE path exists
        anywhere in this module or any caller (invariant 1). Corrections must be new
        ForecastLogRow instances with supersedes_forecast_id set — never a mutation of
        an existing row.'''

Genesis row: prev_row_hash for seq=0 is a well-known constant (e.g. "genesis"),
documented in docs/data-model.md once chosen.
"""
