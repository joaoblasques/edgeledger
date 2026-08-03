# Setting up the schedule

What has to be done by hand to start the twelve-month clock. Everything else is already
committed and working. See [ADR-0003](adr/0003-scheduling-and-storage.md) for why it is
built this way.

The workflow runs **without** R2 — bronze archiving is skipped and forecasts are still
written and committed. So step 1 is optional if you only want the forecast log; it is
required to keep raw order books for the feature work in months 5–12.

---

## 1. Cloudflare R2 bucket (~10 minutes)

R2 is S3-compatible with no egress fees. About $0.40/month at this volume.

1. Sign in at **dash.cloudflare.com** → **R2** in the sidebar → **Create bucket**
2. Name it `edgeledger-bronze`. Location: automatic. No public access.
3. Copy your **Account ID** — it is in the R2 sidebar, and in the dashboard URL:
   `dash.cloudflare.com/<ACCOUNT_ID>/r2`
4. **Manage R2 API Tokens** → **Create API token**
   - Permission: **Object Read & Write**
   - Scope it to the `edgeledger-bronze` bucket only
   - TTL: no expiry (or set a reminder to rotate)
5. Copy the **Access Key ID** and **Secret Access Key**. The secret is shown **once**.

## 2. Add the GitHub secrets (~2 minutes)

Repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.
Four secrets, named exactly:

| Name | Value |
|---|---|
| `R2_ACCOUNT_ID` | your Cloudflare account ID |
| `R2_ACCESS_KEY_ID` | from step 1.5 |
| `R2_SECRET_ACCESS_KEY` | from step 1.5 |
| `R2_BUCKET` | `edgeledger-bronze` |

Or from the terminal:

```
gh secret set R2_ACCOUNT_ID
gh secret set R2_ACCESS_KEY_ID
gh secret set R2_SECRET_ACCESS_KEY
gh secret set R2_BUCKET
```

Each prompts for the value, so nothing lands in your shell history.

For local runs, put the same four in `.env` (already gitignored).

## 3. Check it works (~1 minute)

```
gh workflow run forecast.yml
gh run watch
```

The run summary shows the JSON: markets ingested, forecasts written, rows in the log, and
the chain head. A successful run commits `data/forecast_log.jsonl` and
`docs/chain-head.json` back to `master`.

To verify R2 specifically:

```
uv run python3 -c "from edgeledger.archive import verify_connection; print(verify_connection())"
```

`True` means the bucket is reachable and the credentials work.

## 4. Nothing else

The schedule is already live in `.github/workflows/forecast.yml` (`0 */6 * * *`). It will
start on its own. GitHub delays scheduled runs under load — that is expected and harmless,
because every forecast row carries its own `capture_ts_utc` and a late run is still an
honest one.

---

## Verifying the chain (anyone can do this)

The point of the whole exercise. No credentials needed:

```
git clone https://github.com/joaoblasques/edgeledger
cd edgeledger && uv sync
uv run python3 -c "
from pathlib import Path
from edgeledger.forecast.log import read_rows, verify_chain, head_hash
rows = read_rows(Path('data'))
verify_chain(rows)
print(f'{len(rows)} rows verify. Head: {head_hash(Path(\"data\"))}')
"
```

Compare that head hash against `docs/chain-head.json`. If a single forecast had been
edited after the fact, the recomputed chain would not match.

## Running a cycle by hand

```
uv run python3 -m edgeledger.scheduled_run --data-dir data --no-archive
```

`--no-archive` skips R2. Add `--market-pages 1 --book-limit 3` for a fast smoke test.

## If a run fails

- **Chain verification failed** — the log is corrupt or was edited. This is the one
  failure that stops everything; investigate before running again, because every
  subsequent row chains onto a broken head.
- **Venue outage** — the run succeeds with `forecasts: 0` and a non-null `ingest_error`.
  Nothing to do; the next cycle recovers.
- **Archive failed** — `archive_failed` is non-zero in the summary. Forecasts were still
  written. Check the R2 credentials.
