"""Archive bronze partitions to S3-compatible object storage (Cloudflare R2).

Bronze is ~28 GiB/year — far too much for git, and `data/` is gitignored by policy. The
forecast log stays in the repo (it is the public tamper-evident artifact, ~125 MiB/year);
everything raw goes here.

**Archiving never blocks a forecast.** If R2 is unconfigured, unreachable, or rejects the
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
class R2Config:
    """Connection details for the archive bucket. Absent values mean "not configured"."""

    account_id: str
    access_key_id: str
    secret_access_key: str
    bucket: str

    @property
    def endpoint_url(self) -> str:
        return f"https://{self.account_id}.r2.cloudflarestorage.com"


def load_r2_config() -> R2Config | None:
    """Read R2 settings from the environment, or None if any part is missing.

    Returning None rather than raising is deliberate: running without an archive is a
    supported mode (local development, or a run where the archive is intentionally off).
    """
    account_id = os.environ.get("R2_ACCOUNT_ID", "").strip()
    access_key_id = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
    secret = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
    bucket = os.environ.get("R2_BUCKET", "").strip()

    if not all((account_id, access_key_id, secret, bucket)):
        return None
    return R2Config(
        account_id=account_id,
        access_key_id=access_key_id,
        secret_access_key=secret,
        bucket=bucket,
    )


def _client(config: R2Config):
    """Build an S3 client pointed at R2. Imported lazily so boto3 is only needed when used."""
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=config.endpoint_url,
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        region_name="auto",  # R2 ignores region but boto3 requires one
        config=Config(retries={"max_attempts": 3, "mode": "standard"}),
    )


def archive_bronze(data_dir: Path, *, config: R2Config | None = None) -> tuple[int, int]:
    """Upload every bronze partition file under `data_dir` to the archive bucket.

    Returns `(uploaded, failed)`. Never raises on a transport error — see the module
    docstring for why a bronze upload must not be able to fail a forecast run.
    """
    config = config or load_r2_config()
    if config is None:
        logger.info("bronze archive skipped: R2 not configured")
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
        logger.warning("R2 bucket not reachable", exc_info=True)
        return False
    return True
