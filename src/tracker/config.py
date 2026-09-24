"""Settings, loaded from environment variables or .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "sqlite:///tracker.db"

    mail_to: str = ""
    mail_from: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""

    enable_gmail: bool = True
    gmail_credentials_file: str = "credentials.json"
    gmail_token_file: str = "token.json"
    gmail_query: str = "from:(careercentre.me) newer_than:7d"
    gmail_max_results: int = 50

    enable_workday: bool = True
    workday_search_text: str = ""
    workday_delay_seconds: float = Field(default=2.0, ge=1.0)
    workday_max_pages: int = Field(default=5, ge=1, le=20)

    enable_greenhouse: bool = True
    # Comma-separated Greenhouse board tokens, e.g. "cultureamp,canva".
    greenhouse_boards: str = "cultureamp"
    greenhouse_delay_seconds: float = Field(default=1.0, ge=0.5)

    @property
    def greenhouse_board_list(self) -> list[str]:
        return [t.strip() for t in self.greenhouse_boards.split(",") if t.strip()]

    notify_min_score: int = Field(default=0, ge=0, le=100)
    notify_max_per_run: int = Field(default=60, ge=1)
    log_level: str = "INFO"

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_username and self.smtp_password and self.mail_to)


@lru_cache
def get_settings() -> Settings:
    return Settings()
