# ADR-0003: GitHub Actions Scheduling, Split Storage

## Status

Accepted — 2026-08-03

## Context

The twelve-month clock needs a scheduler that runs unattended. A missed window is a
permanently lost observation: an order book cannot be reconstructed three hours after the
fact, so "catch up later" does not exist for this data.

The obvious candidate was the operator's MacBook (via `launchd` or a local Airflow), which
is free and already has the four DAGs working. It was rejected: a laptop travels, closes,
and loses network, and a twelve-month public commitment that quietly stops in month three
is worse than one that never started.

Storage forced a second decision. Measured against the live venue, the pipeline produces:

| Data | Volume | Notes |
|---|---|---|
| Bronze (books, trades, snapshots) | **~28 GiB/year** | at 15-min ingestion |
| Forecast log | **~160 MiB/year** | measured at 1,150 B/row, 100 markets, 6-hourly |

A GitHub Actions runner is ephemeral, so anything that must survive between runs has to be
pushed somewhere. 28 GiB cannot go in git, and `CLAUDE.md` forbids staging anything under
`data/`. But the forecast log *must* be publicly readable — publishing the chain head is
the entire tamper-evidence mechanism, and a verifier who cannot read the log cannot check
the chain.

## Decision

**Schedule on GitHub Actions. Split storage by purpose.**

- `.github/workflows/forecast.yml` runs every 6 hours (`0 */6 * * *`), matching the
  cadence already documented in `docs/methodology.md`.
- **The forecast log is committed to the repository.** `.gitignore` uses `data/*` with an
  explicit `!data/forecast_log.jsonl` negation. (`data/` would not work: excluding the
  directory stops git descending into it and silently kills the negation.)
- **Bronze is archived to Cloudflare R2** (`src/edgeledger/archive.py`), S3-compatible with
  no egress fees. Object keys mirror the on-disk partition layout.
- `docs/chain-head.json` is republished every run: head hash, row count, timestamp.
- `concurrency: forecast-log` with `cancel-in-progress: false` serialises runs. Two
  concurrent runs minting `seq` from the same chain would race (invariant 5), and the
  writer would reject the second — a loud failure, but one that should not be reachable.

**Failure behaviour is asymmetric, by design:**

- A **venue outage** does not fail the run. Zero forecasts because Polymarket was down is
  a true observation; the schedule keeps its cadence and the next run recovers.
- An **archive failure** does not fail the run. Bronze loss costs feature history; a
  failed forecast costs a permanently missing row in the credibility artifact.
- A **chain verification failure** fails the run immediately and loudly. Publishing an
  unverifiable log is the one outcome worth stopping everything for.

## Consequences

**Easier:** no server, no scheduler daemon, no machine of the operator's involved. The
log is public and verifiable straight from the repo — `verify_chain` over
`data/forecast_log.jsonl` needs no credentials and no external service.

**Harder:** GitHub delays scheduled workflows under load and disables them after 60 days
of repository inactivity. The 60-day rule is not a practical risk here (the workflow
commits every 6 hours, which *is* activity), but delay is real. This is acceptable
precisely because every row carries its own `capture_ts_utc`: a late run is still an honest
run, and the log records when the forecast actually happened rather than when it was
scheduled.

**Cost:** R2 at ~28 GiB/year is roughly $0.40/month, with free egress. Actions minutes are
free for a public repository.

**Forecloses:** nothing. The four Airflow DAGs remain valid and untouched — if this moves
to a real server later, they are the deployment path, and `scheduled_run.py` is what they
would call anyway.

## Related

- `.github/workflows/forecast.yml` — the schedule.
- `src/edgeledger/scheduled_run.py` — one cycle: ingest → forecast → archive → verify.
- `src/edgeledger/archive.py` — R2 upload, best-effort by design.
- `docs/setup-scheduling.md` — the credential steps the operator must do by hand.
