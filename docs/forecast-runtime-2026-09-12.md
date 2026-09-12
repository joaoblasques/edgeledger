# Forecast runtime: why runs are being cancelled, and what actually fixes it

Date: 2026-09-12
Status: timeout raised 20 → 45 (stopgap, shipped). Real fix NOT implemented.

## Symptom

13 of the last 30 scheduled `forecast.yml` runs were **cancelled** at
`timeout-minutes: 20`. Each cancellation is a permanently missed forecast window. The
workflow header is explicit that a missed window is "a gap, never a falsified row" —
so this is not corrupting data, but it is silently thinning an already-thin sample.

## Measurement

60 runs analysed via `gh run list`, durations computed from `createdAt`/`updatedAt`:

```
success:    47   min=11.3  median=17.1  max=20.1 min
cancelled:  13   median=20.4 min  (= the wall)
```

Median successful runtime **by week**:

| Week | n | median | max |
|---|---|---|---|
| 2026-08-w4 | 4 | 14.8 | 14.9 |
| 2026-08-w5 | 10 | 15.1 | 16.2 |
| 2026-09-w1 | 26 | 17.9 | 20.1 |
| 2026-09-w2 | 7 | 19.0 | 20.0 |

This is not a fixed-cost job bumping an arbitrary ceiling. **Runtime is growing
steadily** — ~4 minutes of median growth in four weeks — and successful runs now touch
20.1 min, i.e. they are finishing only just inside the wall.

## Root cause: the append path is O(markets × accumulated rows)

`src/edgeledger/forecast/log.py` reads the log by fully parsing it:

```python
def read_rows(data_dir: Path) -> list[ForecastLogRow]:
    """Read every row, in seq order."""
    ...
    return [ForecastLogRow.model_validate_json(line) for line in handle if line.strip()]
```

Every row is Pydantic-validated from line 1 on each call. `head_hash`, `next_seq` and
`verify_chain` all call it.

**Three full reads happen per appended row:**

1. `src/edgeledger/forecast/runner.py:190` — `seq=next_seq(data_dir)`, evaluated
   **inside the per-market loop**.
2. `log.py` `append_row` → `expected_seq = next_seq(data_dir)` (a second full read, to
   validate the seq the caller just computed).
3. `log.py` `append_row` → `prev_hash = head_hash(data_dir)` (a third full read, to get
   only the *last* row's hash).

So the cost of one forecast cycle scales with `markets_forecast × rows_already_logged`.
The log is append-only and permanent — it stood at 29,600 rows three weeks ago — so
this term grows every single run, forever. The observed curve is exactly that shape.

Note that read #3 walks and validates the entire file to obtain one field of the final
line, and read #2 re-derives a value the caller already holds.

## Why the timeout raise is only a stopgap

At ~1 min of median growth per week, `timeout-minutes: 45` buys roughly **six months**
from today's 19 min — better than the ~6 weeks a raise to 30 would have bought, but
still a deadline, not a solution. The project's horizon was just extended to two years
(`docs/horizon-change-2026-09-12.md`), which guarantees this recurs, and the growth is
super-linear in wall-clock terms because the log grows with every run.

Raising the ceiling was still the right first move: it stops active data loss today
without touching the append path, which is the most correctness-critical code in the
repo (invariants 1–5 all live there).

## The real fix

Ordered by payoff against risk. **None of these may weaken invariants 1–5** — the
append-only guarantee and the hash chain are the project's entire differentiator.

1. **Stop re-reading inside the loop.** `runner.py:190` should mint seq once per cycle
   and increment in memory, or `append_row` should return the seq it wrote. This alone
   removes one of three full reads per row.
2. **Make `head_hash` and `next_seq` O(1).** Both need only the final line. Read the
   file's tail rather than parsing every row, or maintain a small sidecar head file
   (`head.json`: `{seq, row_hash}`) written atomically alongside each append. The
   sidecar must be treated as a *cache*, never as the source of truth — it is
   rebuildable from the log, and a mismatch should fail loudly.
3. **Make `append_row` take the previous hash as a parameter** when the caller already
   knows it, so a batch of appends walks the chain once rather than once per row.
4. **Leave `verify_chain` O(n) and keep calling it once per run.** It is the function
   an outside reviewer runs, and its whole value is that it recomputes everything from
   genesis. Optimising it would undermine the guarantee it exists to provide. One full
   pass per cycle is the correct cost.

Expected effect of 1–3: per-cycle cost drops from `O(markets × rows)` to
`O(markets) + O(rows)`, where the `O(rows)` term is the single deliberate
`verify_chain` pass.

## Verification when the real fix lands

- `verify_chain` must still pass from genesis over the full existing log.
- Seq must remain gapless and monotonic across the change (invariant 5) — in
  particular, a crashed mid-cycle run must not leave a skipped number. The current
  design derives seq from disk precisely to prevent this, so any in-memory counter must
  re-derive from disk at cycle start and never persist across a failure.
- No existing row's `row_hash` may change. Recompute the published head hash before and
  after; they must be identical.
