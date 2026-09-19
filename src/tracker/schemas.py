"""Models for data crossing a boundary."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RawPosting(BaseModel):
    """What a parser or source produces. Deliberately loose: real data is messy."""

    title: str
    company: str | None = None
    location: str | None = None
    url: str | None = None
    description: str | None = None
    source: str
    posted_at: datetime | None = None
    closes_at: datetime | None = None


class RunResult(BaseModel):
    messages_fetched: int = 0
    postings_parsed: int = 0
    jobs_created: int = 0
    jobs_updated: int = 0
    jobs_emailed: int = 0
    email_sent: bool = False
    errors: list[str] = []
