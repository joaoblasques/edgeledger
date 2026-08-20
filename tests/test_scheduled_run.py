"""Tests for the scheduled cycle and the bronze archiver (Backblaze B2 / Cloudflare R2).

The properties that matter here are about failure behaviour: an unattended twelve-month
schedule must degrade in the right direction. A venue outage or a dead archive must not
stop a forecast being written; a corrupt log must stop everything.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from edgeledger.archive import (
    ArchiveConfig,
    archive_bronze,
    load_archive_config,
)
from edgeledger.bronze.schemas import VenueMarketSnapshot
from edgeledger.bronze.writers import write_rows
from edgeledger.forecast.log import read_rows
from edgeledger.scheduled_run import run_cycle

NOW = datetime.now(UTC)


def _snapshot(market_id: str = "m1", *, bid: float = 0.40, ask: float = 0.50):
    return VenueMarketSnapshot(
        capture_ts_utc=NOW,
        run_id="seed",
        venue="polymarket",
        venue_market_id=market_id,
        payload=json.dumps(
            {"question": "Will it?", "conditionId": market_id, "bestBid": bid, "bestAsk": ask}
        ),
        ingest_date=NOW.date(),
    )


# --- archive configuration ------------------------------------------------------------


def test_r2_config_absent_when_env_incomplete(monkeypatch):
    """A half-configured archive must read as unconfigured, not as broken credentials."""
    monkeypatch.setenv("R2_ACCOUNT_ID", "acct")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
    monkeypatch.delenv("R2_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.setenv("R2_BUCKET", "bucket")

    assert load_archive_config() is None


def test_r2_config_loads_when_complete(monkeypatch):
    for name, value in [
        ("R2_ACCOUNT_ID", "acct"),
        ("R2_ACCESS_KEY_ID", "key"),
        ("R2_SECRET_ACCESS_KEY", "secret"),
        ("R2_BUCKET", "bucket"),
    ]:
        monkeypatch.setenv(name, value)

    config = load_archive_config()
    assert config is not None
    assert config.endpoint_url == "https://acct.r2.cloudflarestorage.com"


B2_ENV = {
    "B2_KEY_ID": "0035abc",
    "B2_APPLICATION_KEY": "K003secret",
    "B2_BUCKET": "edgeledger-bronze",
    "B2_ENDPOINT": "s3.eu-central-003.backblazeb2.com",
}


def _set_b2(monkeypatch, **overrides):
    for name in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
        monkeypatch.delenv(name, raising=False)
    for name, value in {**B2_ENV, **overrides}.items():
        monkeypatch.setenv(name, value)


def test_b2_config_loads_and_derives_region(monkeypatch):
    """B2 validates the region and rejects a mismatch with SignatureDoesNotMatch, which
    reads as a credential problem. It is parsed from the endpoint, never guessed."""
    _set_b2(monkeypatch)

    config = load_archive_config()

    assert config is not None
    assert config.endpoint_url == "https://s3.eu-central-003.backblazeb2.com"
    assert config.region == "eu-central-003"
    assert config.bucket == "edgeledger-bronze"


def test_b2_endpoint_accepts_a_pasted_https_url(monkeypatch):
    """Backblaze's console shows the endpoint bare, but pasting the full URL is the
    obvious mistake to make — accept both rather than failing obscurely."""
    _set_b2(monkeypatch, B2_ENDPOINT="https://s3.us-west-004.backblazeb2.com/")

    config = load_archive_config()

    assert config is not None
    assert config.endpoint_url == "https://s3.us-west-004.backblazeb2.com"
    assert config.region == "us-west-004"


def test_b2_takes_precedence_when_both_are_configured(monkeypatch):
    _set_b2(monkeypatch)
    monkeypatch.setenv("R2_ACCOUNT_ID", "acct")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("R2_BUCKET", "r2-bucket")

    config = load_archive_config()

    assert config is not None
    assert "backblazeb2.com" in config.endpoint_url


def test_partial_b2_config_is_unconfigured(monkeypatch):
    _set_b2(monkeypatch)
    monkeypatch.delenv("B2_APPLICATION_KEY")

    assert load_archive_config() is None


def test_blank_env_values_count_as_unconfigured(monkeypatch):
    """GitHub Actions injects empty strings for secrets that were never set."""
    for name in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
        monkeypatch.setenv(name, "  ")
    assert load_archive_config() is None


def test_archive_is_a_noop_without_config(tmp_path, monkeypatch):
    for name in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
        monkeypatch.delenv(name, raising=False)
    write_rows([_snapshot()], tmp_path, run_id="r1")

    assert archive_bronze(tmp_path) == (0, 0)


def test_archive_failure_is_reported_not_raised(tmp_path, monkeypatch):
    """A dead bucket must not raise — bronze loss is survivable, a failed run is not.

    The client is stubbed rather than pointed at a bad endpoint: a real connection would
    spend two minutes in DNS and boto3 retries, and a slow suite stops being run.
    """
    from botocore.exceptions import EndpointConnectionError

    write_rows([_snapshot()], tmp_path, run_id="r1")

    class DeadClient:
        def upload_file(self, *args, **kwargs):
            raise EndpointConnectionError(endpoint_url="https://unreachable.invalid")

    monkeypatch.setattr("edgeledger.archive._client", lambda config: DeadClient())
    config = ArchiveConfig(
        access_key_id="k",
        secret_access_key="s",
        bucket="bucket",
        endpoint_url="https://example.invalid",
    )

    uploaded, failed = archive_bronze(tmp_path, config=config)

    assert uploaded == 0
    assert failed >= 1, "the failure must be counted, not swallowed silently"


def test_archive_uploads_every_bronze_partition(tmp_path, monkeypatch):
    """Keys mirror the on-disk layout so a bucket listing reads like the local tree."""
    write_rows([_snapshot("m1"), _snapshot("m2")], tmp_path, run_id="run-a")
    keys: list[str] = []

    class RecordingClient:
        def upload_file(self, path, bucket, key):
            keys.append(key)

    monkeypatch.setattr("edgeledger.archive._client", lambda config: RecordingClient())
    config = ArchiveConfig(
        access_key_id="k",
        secret_access_key="s",
        bucket="bucket",
        endpoint_url="https://example.invalid",
    )

    uploaded, failed = archive_bronze(tmp_path, config=config)

    assert (uploaded, failed) == (1, 0)  # one partition file holds both rows
    assert keys[0].startswith("bronze/venue_market_snapshot/ingest_date=")
    assert keys[0].endswith("run-a.jsonl")


# --- the cycle -------------------------------------------------------------------------


def test_cycle_writes_forecasts_and_verifies_the_chain(tmp_path, monkeypatch):
    """Happy path with ingestion stubbed out — the forecast and verify steps are real."""

    async def fake_ingest(data_dir, run_id, market_pages, book_limit):
        write_rows([_snapshot("m1"), _snapshot("m2")], data_dir, run_id=run_id)
        return {"markets": 2, "books": 0, "ingest_error": None}

    monkeypatch.setattr("edgeledger.scheduled_run._ingest", fake_ingest)

    summary = run_cycle(tmp_path, run_id="test-run", archive=False)

    assert summary["forecasts"] == 2
    assert summary["log_rows"] == 2
    assert len(summary["head_hash"]) == 64
    assert summary["run_id"] == "test-run"


def test_venue_outage_does_not_fail_the_cycle(tmp_path, monkeypatch):
    """Zero forecasts because a venue was down is a true observation, not an error.
    The schedule must keep its cadence."""

    async def failing_ingest(data_dir, run_id, market_pages, book_limit):
        return {"markets": 0, "books": 0, "ingest_error": "RequestError: boom"}

    monkeypatch.setattr("edgeledger.scheduled_run._ingest", failing_ingest)

    summary = run_cycle(tmp_path, run_id="outage", archive=False)

    assert summary["forecasts"] == 0
    assert summary["ingest_error"] is not None
    assert summary["log_rows"] == 0


def test_corrupt_log_fails_the_cycle(tmp_path, monkeypatch):
    """The one condition that must stop everything: a chain that does not verify."""

    async def fake_ingest(data_dir, run_id, market_pages, book_limit):
        write_rows([_snapshot("m1")], data_dir, run_id=run_id)
        return {"markets": 1, "books": 0, "ingest_error": None}

    monkeypatch.setattr("edgeledger.scheduled_run._ingest", fake_ingest)
    run_cycle(tmp_path, run_id="first", archive=False)

    # Tamper with the committed log exactly as a dishonest operator would.
    log = tmp_path / "forecast_log.jsonl"
    text = log.read_text().replace('"p_hat":"0.45"', '"p_hat":"0.99"')
    log.write_text(text)

    with pytest.raises(ValueError, match="altered|chain|seq"):
        run_cycle(tmp_path, run_id="second", archive=False)


def test_cycle_appends_across_runs(tmp_path, monkeypatch):
    """Consecutive scheduled runs extend one chain rather than restarting it."""
    counter = {"n": 0}

    async def fake_ingest(data_dir, run_id, market_pages, book_limit):
        counter["n"] += 1
        write_rows([_snapshot(f"m{counter['n']}")], data_dir, run_id=run_id)
        return {"markets": 1, "books": 0, "ingest_error": None}

    monkeypatch.setattr("edgeledger.scheduled_run._ingest", fake_ingest)

    run_cycle(tmp_path, run_id="run-1", archive=False)
    second = run_cycle(tmp_path, run_id="run-2", archive=False)

    rows = read_rows(Path(tmp_path))
    assert second["log_rows"] == len(rows)
    assert [r.seq for r in rows] == list(range(len(rows))), "gapless across scheduled runs"
    assert {r.run_id for r in rows} == {"run-1", "run-2"}


def test_cycle_ingests_resolutions(tmp_path, monkeypatch):
    """Regression: resolutions were implemented but never called by the scheduled cycle,
    so every forecast was permanently unscoreable. Stubs the venue calls, not `_ingest`."""
    called: dict[str, str] = {}

    async def fake_markets(data_dir, *, run_id, max_pages):
        return []

    async def fake_books(markets, data_dir, *, run_id, limit):
        return 0

    async def fake_resolutions(data_dir, *, run_id):
        called["run_id"] = run_id
        return 7

    monkeypatch.setattr("edgeledger.scheduled_run.ingest_polymarket_markets", fake_markets)
    monkeypatch.setattr("edgeledger.scheduled_run.ingest_polymarket_books", fake_books)
    monkeypatch.setattr(
        "edgeledger.scheduled_run.ingest_polymarket_resolutions_for_forecast_markets",
        fake_resolutions,
    )

    summary = run_cycle(tmp_path, run_id="res-run", archive=False)

    assert called["run_id"] == "res-run", "resolutions must be polled every cycle"
    assert summary["resolutions"] == 7
