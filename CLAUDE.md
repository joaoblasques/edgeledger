# CLAUDE.md — EdgeLedger

**Purpose:** EdgeLedger is a twelve-month research system for prediction markets, built as a
hiring portfolio for a quantitative researcher / trading-systems role on an event-contract desk.

**The pitch:** *"I build the measurement and modelling layer that lets a desk know whether its
edge is real — and I have twelve months of timestamped, out-of-sample forecasts to prove the
layer works."*

Pregame-only, systematic, hold-to-resolution. No live/in-game trading, ever. The system runs
unattended.

---

## Design Invariants — Non-Negotiable

These are the credibility of the entire project. Encode them in code, tests, and this file.
Never relax them for convenience.

1. **The forecast log is append-only.** No UPDATE, no DELETE, ever. Corrections are new rows
   carrying `supersedes_forecast_id`. Enforce in the writer; assert in tests.

2. **Market state is captured at forecast write time, never joined afterwards.** Joining price
   after the fact destroys CLV and is the first thing an interviewer will check.

3. **`feature_cutoff_ts_utc` is a contract.** Every feature must be derivable from rows with
   `capture_ts_utc <= feature_cutoff_ts_utc`. `tests/test_point_in_time.py` must assert this.
   This is the leakage firewall.

4. **Hash chain for tamper evidence.** `row_hash = sha256(prev_row_hash + canonical_json(row_minus_hashes))`.
   Daily head hash published to the repo. This converts "trust me" into proof.

5. **`seq` is gapless and monotonic.** A gap means a lost write. Monitor it.

6. **Every metric is reported against the market baseline.** `brier_market` alongside `brier`,
   always. Absolute accuracy numbers are meaningless.

7. **Everything UTC.** No local timezones anywhere, including sports schedules.

8. **`capture_ts_utc` (ours) and venue timestamps are both stored, never reconciled into one
   field.**

---

## Automation Boundary

**Agent-owned:** client boilerplate, retry/backoff, pagination, DAG scaffolding, pydantic
models from JSON samples, test generation, Delta helpers, refactors.

**Human-owned, never auto-decided:** forecast log schema changes, the point-in-time contract,
hash-chain design, which markets to track, resolution-criteria interpretation, sizing rules,
methodology doc.

---

## Coding Standards

- Type hints everywhere.
- Pydantic for all boundaries (API responses, config, table rows).
- No bare `except:` — catch specific exceptions.
- Structured logging (no bare `print`).
- No secrets in code. Ever. Config comes from `.env` / `pydantic-settings`.

---

## Before You Commit

- [ ] `ruff check .` is clean
- [ ] `pytest` passes (or fails only against known-stub modules, and that's stated in the PR/commit)
- [ ] Nothing under `data/` is staged
- [ ] An ADR is written in `docs/adr/` if a design invariant above was touched
- [ ] `docs/methodology.md` is updated if scoring logic changed
