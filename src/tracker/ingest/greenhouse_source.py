"""Company job boards hosted on Greenhouse.

Why this source exists
----------------------
RMIT Careers only ever advertises RMIT's own vacancies, which are overwhelmingly
university staff roles. The Career Centre path depends on someone else's alert
schedule and, in practice, delivers a link to a list rather than the list itself.
Neither puts graduate software roles in the digest.

Greenhouse does. Hundreds of companies use it as their applicant tracking system,
and every Greenhouse board exposes a public, documented JSON endpoint:

    https://boards-api.greenhouse.io/v1/boards/<token>/jobs

No authentication, no scraping, no reverse engineering. ADR 0001 ranks sources as
published feed, official email alerts, official API, then the site's own public
endpoint. This is an official API, which puts it above the Workday source we
already rely on.

Finding a board token
---------------------
Open a company's careers page. If the URL looks like

    https://boards.greenhouse.io/cultureamp
    https://job-boards.greenhouse.io/cultureamp

then `cultureamp` is the token. If the careers page is on the company's own
domain, the listings are usually in an iframe whose src carries the same token.
Companies that do not use Greenhouse simply 404, which this source treats as a
skip rather than a failure.

Set GREENHOUSE_BOARDS in .env to a comma-separated list of tokens.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

import httpx

from tracker.config import get_settings
from tracker.ingest.base import PostingSource
from tracker.schemas import RawPosting

logger = logging.getLogger(__name__)

SOURCE_NAME = "greenhouse"
API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
USER_AGENT = "rmit-job-mailer (personal job digest; +https://github.com/Kanav-Midha/rmit-job-mailer)"


def _parse_when(value: str | None) -> datetime | None:
    """Greenhouse sends ISO 8601. Anything else is not worth guessing at."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def to_posting(job: dict, company: str) -> RawPosting | None:
    """Convert one Greenhouse job object into a RawPosting.

    Returns None when the job has no title, which would otherwise become an
    'Untitled role' row that nobody can act on.
    """
    title = (job.get("title") or "").strip()
    if not title:
        return None

    location = (job.get("location") or {}).get("name")

    return RawPosting(
        title=title,
        company=company,
        location=location.strip() if location else None,
        url=job.get("absolute_url"),
        # The list endpoint omits the body. Location and title carry enough for
        # classification; fetching each job individually would be one request per
        # posting for a description the digest truncates anyway.
        description=None,
        source=SOURCE_NAME,
        posted_at=_parse_when(job.get("first_published") or job.get("updated_at")),
        closes_at=_parse_when(job.get("application_deadline")),
    )


class GreenhouseSource(PostingSource):
    """Reads every configured Greenhouse board and returns their postings."""

    name = SOURCE_NAME

    def __init__(self, tokens: list[str] | None = None, delay: float | None = None) -> None:
        settings = get_settings()
        self.tokens = tokens if tokens is not None else settings.greenhouse_board_list
        self.delay = settings.greenhouse_delay_seconds if delay is None else delay

    def _fetch_board(self, client: httpx.Client, token: str) -> list[RawPosting]:
        response = client.get(API.format(token=token))

        if response.status_code == 404:
            logger.warning(
                "Greenhouse board %r does not exist. Check the token against the "
                "company's careers page URL.",
                token,
            )
            return []
        response.raise_for_status()

        jobs = response.json().get("jobs", [])
        company = token.replace("-", " ").title()
        postings = [p for p in (to_posting(job, company) for job in jobs) if p]

        logger.info("Greenhouse board %r returned %s postings", token, len(postings))
        return postings

    def fetch(self) -> list[RawPosting]:
        if not self.tokens:
            logger.info("No Greenhouse boards configured; set GREENHOUSE_BOARDS in .env.")
            return []

        postings: list[RawPosting] = []
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}

        with httpx.Client(timeout=20.0, headers=headers, follow_redirects=True) as client:
            for index, token in enumerate(self.tokens):
                if index:
                    time.sleep(self.delay)
                try:
                    postings.extend(self._fetch_board(client, token))
                except Exception as exc:
                    # One bad board must not cost us the others, or the run.
                    logger.error("Greenhouse board %r failed: %s", token, exc)

        return postings
