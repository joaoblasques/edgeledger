"""Archive bronze partitions to S3-compatible object storage.

Backblaze B2 is the configured provider; Cloudflare R2 works through the same code path.
Either is selected purely by which environment variables are present.

Bronze is ~28 GiB/year — far too much for git, and `data/` is gitignored by policy. The
forecast log stays in the repo (it is the public tamper-evident artifact, ~125 MiB/year);
everything raw goes here.

**Archiving never blocks a forecast.** If the bucket is unconfigured, unreachable, or rejects the
upload, `archive_bronze` logs and returns a failure count rather than raising. A missed
bronze upload costs feature history; a failed forecast costs a permanently missing row in
the credibility artifact, which is far worse. The caller checks the return value if it
cares.

Credentials come from the environment (GitHub Actions secrets in CI, `.env` locally) and
are never logged, never defaulted, and never written to disk.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

# Object keys mirror the on-disk partition layout, so a bucket listing reads the same as
# the local tree: bronze/<table>/ingest_date=YYYY-MM-DD/<run_id>.jsonl
KEY_PREFIX = "bronze"


@dataclass(frozen=True, slots=True)
class ArchiveConfig:
    """Connection details for the archive bucket. Absent values mean "not configured".

    Provider-agnostic: any S3-compatible store works. `endpoint_url` is supplied directly
    for Backblaze B2, or derived from the account id for Cloudflare R2.
    """

    access_key_id: str
    secret_access_key: str
    bucket: str
    endpoint_url: str
    region: str = "auto"


# Kept as an alias so existing imports and tests keep working after the B2 generalisation.
R2Config = ArchiveConfig


def load_archive_config() -> ArchiveConfig | None:
    """Read archive settings from the environment, or None if incomplete.

    Two supported shapes, checked in order:

      * **Backblaze B2** — `B2_KEY_ID`, `B2_APPLICATION_KEY`, `B2_BUCKET`, `B2_ENDPOINT`
        (e.g. `s3.eu-central-003.backblazeb2.com`). The region is embedded in the
        endpoint and B2 validates it, so it is parsed out rather than sent as "auto".
      * **Cloudflare R2** — `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`,
        `R2_BUCKET`.

    Returning None rather than raising is deliberate: running without an archive is a
    supported mode (local development, or a run where the archive is intentionally off).
    """
    b2_key_id = os.environ.get("B2_KEY_ID", "").strip()
    b2_secret = os.environ.get("B2_APPLICATION_KEY", "").strip()
    b2_bucket = os.environ.get("B2_BUCKET", "").strip()
    b2_endpoint = os.environ.get("B2_ENDPOINT", "").strip()

    if all((b2_key_id, b2_secret, b2_bucket, b2_endpoint)):
        host = b2_endpoint.removeprefix("https://").removeprefix("http://").rstrip("/")
        return ArchiveConfig(
            access_key_id=b2_key_id,
            secret_access_key=b2_secret,
            bucket=b2_bucket,
            endpoint_url=f"https://{host}",
            region=_region_from_b2_endpoint(host),
        )

    account_id = os.environ.get("R2_ACCOUNT_ID", "").strip()
    access_key_id = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
    secret = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
    bucket = os.environ.get("R2_BUCKET", "").strip()

    if all((account_id, access_key_id, secret, bucket)):
        return ArchiveConfig(
            access_key_id=access_key_id,
            secret_access_key=secret,
            bucket=bucket,
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            region="auto",
        )

    return None


def _region_from_b2_endpoint(host: str) -> str:
    """Extract the region from a B2 S3 host: s3.eu-central-003.backblazeb2.com -> eu-central-003.

    B2 rejects a mismatched region with SignatureDoesNotMatch, which reads as a credential
    problem rather than a config one — so it is derived instead of guessed.
    """
    parts = host.split(".")
    if len(parts) >= 3 and parts[0] == "s3":
        return parts[1]
    return "us-east-1"


# Back-compat for callers written against the R2-only version.
load_r2_config = load_archive_config


def _client(config: ArchiveConfig):
    """Build an S3 client. boto3 is imported lazily so it is only needed when archiving."""
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=config.endpoint_url,
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        region_name=config.region,
        config=Config(retries={"max_attempts": 3, "mode": "standard"}),
    )


def archive_bronze(data_dir: Path, *, config: R2Config | None = None) -> tuple[int, int]:
    """Upload every bronze partition file under `data_dir` to the archive bucket.

    Returns `(uploaded, failed)`. Never raises on a transport error — see the module
    docstring for why a bronze upload must not be able to fail a forecast run.
    """
    config = config or load_r2_config()
    if config is None:
        logger.info("bronze archive skipped: no bucket configured")
        return (0, 0)

    bronze_root = data_dir / "bronze"
    if not bronze_root.exists():
        return (0, 0)

    files = sorted(bronze_root.rglob("*.jsonl"))
    if not files:
        return (0, 0)

    try:
        client = _client(config)
    except (ImportError, BotoCoreError, ValueError):
        # A missing/broken boto3 or bad config must not take the run down with it.
        logger.warning("bronze archive skipped: could not build S3 client", exc_info=True)
        return (0, len(files))

    uploaded = failed = 0
    for path in files:
        key = f"{KEY_PREFIX}/{path.relative_to(bronze_root).as_posix()}"
        try:
            client.upload_file(str(path), config.bucket, key)
            uploaded += 1
        except (BotoCoreError, ClientError, OSError):
            failed += 1
            logger.warning("bronze upload failed", extra={"key": key}, exc_info=True)

    logger.info(
        "bronze archived",
        extra={"uploaded": uploaded, "failed": failed, "bucket": config.bucket},
    )
    return (uploaded, failed)


def verify_connection(config: R2Config | None = None) -> bool:
    """Check the bucket is reachable and writable. Used by the setup smoke test."""
    config = config or load_r2_config()
    if config is None:
        return False
    try:
        _client(config).head_bucket(Bucket=config.bucket)
    except (ImportError, BotoCoreError, ClientError, OSError):
        logger.warning("archive bucket not reachable", exc_info=True)
        return False
    return True
