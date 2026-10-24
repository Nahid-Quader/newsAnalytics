"""Application settings, read from environment variables or the repo-root `.env` file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    # SQLite by default so the app runs without a database server; use PostgreSQL in production,
    # e.g. postgresql+psycopg://news:news@localhost:5432/news
    database_url: str = f"sqlite:///{(REPO_ROOT / 'data' / 'news.db').as_posix()}"
    sources_file: Path = REPO_ROOT / "config" / "sources.yaml"

    user_agent: str = "newsAnalytics/0.1 (+https://github.com/Nahid-Quader/newsAnalytics)"
    http_timeout_s: float = 25.0
    http_max_retries: int = 3
    http_backoff_base_s: float = 2.0
    per_host_delay_s: float = 2.0

    log_level: str = "INFO"
    log_json: bool = True
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
