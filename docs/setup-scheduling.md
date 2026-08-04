# Setting up the schedule

What has to be done by hand to start the twelve-month clock. Everything else is already
committed and working. See [ADR-0003](adr/0003-scheduling-and-storage.md) for why it is
built this way.

The workflow runs **without** an archive bucket — bronze archiving is skipped and forecasts are still
written and committed. So step 1 is optional if you only want the forecast log; it is
required to keep raw order books for the feature work in months 5–12.

---

## 1. Backblaze B2 bucket (~8 minutes)

B2 is S3-compatible. The free tier is 10 GB of storage with no payment method required,
which covers the whole first year at the 6-hourly cadence.

1. Sign up at **backblaze.com/sign-up/cloud-storage** (email + password; no card for the
   free tier). Verify your email, and enable two-factor auth when prompted.
2. Left sidebar → **B2 Cloud Storage** → **Buckets** → **Create a Bucket**.
   - **Bucket Unique Name:** `edgeledger-bronze` — B2 bucket names are globally unique
     across all customers, so if it is taken add a suffix (`edgeledger-bronze-jb`) and use
     whatever you chose as `B2_BUCKET` below.
   - **Files in Bucket:** **Private**
   - Default encryption: disabled. Object lock: disabled.
3. Click **Create a Bucket**.
4. On the bucket row, note the **Endpoint**, shown as
   `s3.eu-central-003.backblazeb2.com` (your region digits will differ). Copy it.
5. Left sidebar → **Application Keys** → **Add a New Application Key**.
   - **Name of Key:** `edgeledger-ci`
   - **Allow access to Bucket(s):** select just `edgeledger-bronze` — not "All"
   - **Type of Access:** **Read and Write**
   - Leave the file-prefix and duration fields empty
6. Click **Create New Key**. The next screen shows **keyID** and **applicationKey**.
   The application key is displayed **once** — copy both now.

## 2. Add the GitHub secrets (~2 minutes)

From the terminal, one at a time. Each command prompts for the value, so nothing lands in
your shell history — never pass a secret as a command-line argument.

```
gh secret set B2_KEY_ID
gh secret set B2_APPLICATION_KEY
gh secret set B2_BUCKET
gh secret set B2_ENDPOINT
```

| Secret | Value | From |
|---|---|---|
| `B2_KEY_ID` | the **keyID** | step 1.6 |
| `B2_APPLICATION_KEY` | the **applicationKey** | step 1.6 |
| `B2_BUCKET` | `edgeledger-bronze` | step 1.2 |
| `B2_ENDPOINT` | `s3.<region>.backblazeb2.com` | step 1.4 |

`B2_ENDPOINT` accepts the bare host or a full `https://` URL — both work, and the region
is parsed out of it. Getting the region wrong makes B2 return `SignatureDoesNotMatch`,
which looks like a bad key but is not, so it is derived from the endpoint rather than
guessed.

*(Browser alternative: repo → Settings → Secrets and variables → Actions → New repository
secret, four times.)*

For local runs, put the same four in `.env` (already gitignored) — see `.env.example`.

**Cloudflare R2 instead?** The code supports both. Set `R2_ACCOUNT_ID`,
`R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` and `R2_BUCKET` and leave the B2 ones unset.
If both are configured, B2 wins.

## 3. Check it works (~1 minute)

```
gh workflow run forecast.yml
gh run watch
```

The run summary shows the JSON: markets ingested, forecasts written, rows in the log, and
the chain head. A successful run commits `data/forecast_log.jsonl` and
`docs/chain-head.json` back to `master`.

To verify the archive bucket specifically:

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

`--no-archive` skips the bucket upload. Add `--market-pages 1 --book-limit 3` for a fast smoke test.

## If a run fails

- **Chain verification failed** — the log is corrupt or was edited. This is the one
  failure that stops everything; investigate before running again, because every
  subsequent row chains onto a broken head.
- **Venue outage** — the run succeeds with `forecasts: 0` and a non-null `ingest_error`.
  Nothing to do; the next cycle recovers.
- **Archive failed** — `archive_failed` is non-zero in the summary. Forecasts were still
  written. Check the B2 credentials and endpoint region.
