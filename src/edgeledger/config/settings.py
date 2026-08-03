"""Pydantic-settings config loaded from .env / environment, plus venue config from YAML.

No secret material is ever a default value here — only paths and non-secret config. The
Kalshi private key is referenced by path and read at signing time; the key bytes never
live in settings, never in the repo, and never in a log line (CLAUDE.md: no secrets in
code, ever).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_CONFIG_DIR = Path(__file__).parent
VENUES_PATH = _CONFIG_DIR / "venues.yaml"


class Settings(BaseSettings):
    """Environment-derived config. Populated from `.env` or the process environment."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Optional: only the Kalshi orderbook endpoint needs auth. Everything else — and every
    # Polymarket read API — works unauthenticated, so the pipeline runs without these.
    kalshi_access_key: str | None = None
    kalshi_private_key_path: Path | None = None

    edgeledger_data_dir: Path = Path("./data")

    @field_validator("kalshi_access_key", "kalshi_private_key_path", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        """`.env.example` ships these as empty strings; treat blank as absent."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def kalshi_authenticated(self) -> bool:
        """True only if both halves of the Kalshi credential pair are present."""
        return self.kalshi_access_key is not None and self.kalshi_private_key_path is not None

    def require_kalshi_credentials(self) -> tuple[str, Path]:
        """Return the Kalshi key pair, or explain precisely what's missing.

        Called only by the authenticated orderbook path — an unauthenticated fetch must
        never trip this.
        """
        if not self.kalshi_authenticated:
            raise RuntimeError(
                "Kalshi orderbook access needs KALSHI_ACCESS_KEY and "
                "KALSHI_PRIVATE_KEY_PATH in .env (see .env.example)"
            )
        assert self.kalshi_access_key is not None
        assert self.kalshi_private_key_path is not None
        if not self.kalshi_private_key_path.is_file():
            raise FileNotFoundError(
                f"KALSHI_PRIVATE_KEY_PATH does not point at a file: {self.kalshi_private_key_path}"
            )
        return self.kalshi_access_key, self.kalshi_private_key_path


class KalshiVenueConfig(BaseModel):
    base_url: str
    # None means "not yet confirmed against live docs" — venues.yaml ships it null on
    # purpose. Callers fall back to a deliberately conservative rate.
    rate_limit_per_min: int | None = None
    orderbook_requires_auth: bool = True


class PolymarketVenueConfig(BaseModel):
    gamma_base_url: str
    clob_base_url: str
    data_base_url: str
    gamma_rate_limit_per_min: int
    clob_rate_limit_per_min: int


class VenuesConfig(BaseModel):
    kalshi: KalshiVenueConfig
    polymarket: PolymarketVenueConfig


# Conservative default for any venue whose real limit is still unconfirmed. Being throttled
# costs a retry; being banned costs the dataset.
UNCONFIRMED_RATE_LIMIT_PER_MIN = 30


def _parse_venues_yaml(text: str) -> dict:
    """Read venues.yaml.

    ponytail: this file is flat scalars only, and TOML-ish parsing of it would be a lie.
    We hand-parse the two-level `key:` / `  key: value` shape rather than add a PyYAML
    dependency for ~15 lines. If venues.yaml ever needs lists or nesting, add PyYAML and
    delete this.
    """
    result: dict[str, dict[str, object]] = {}
    section: dict[str, object] | None = None

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" "):
            section = {}
            result[line.rstrip(":").strip()] = section
            continue
        if section is None:
            raise ValueError(f"indented line before any section in venues.yaml: {raw!r}")
        key, _, value = line.strip().partition(":")
        section[key.strip()] = _coerce(value.strip())

    return result


def _coerce(value: str) -> object:
    if value in ("null", "~", ""):
        return None
    if value in ("true", "false"):
        return value == "true"
    if value.isdigit():
        return int(value)
    return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


@lru_cache(maxsize=1)
def get_venues(path: Path | None = None) -> VenuesConfig:
    return VenuesConfig.model_validate(_parse_venues_yaml((path or VENUES_PATH).read_text()))
