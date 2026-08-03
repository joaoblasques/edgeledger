"""Pydantic-settings config loaded from .env / environment. STUB — week 1.

Intended shape:

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(env_file=".env")

        kalshi_access_key: str | None = None
        kalshi_private_key_path: Path | None = None
        edgeledger_data_dir: Path = Path("./data")

No secret material is ever a default value here — only paths and non-secret config.
Due: week 1, alongside clients/base.py.
"""
