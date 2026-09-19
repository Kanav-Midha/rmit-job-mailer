"""RMIT's own careers site (rmit.wd3.myworkdayjobs.com).

This is where RMIT advertises its own roles, including the casual on-campus work
students actually want: student ambassador, library and event assistants, peer
mentors, casual tutoring.

How this reads the site
-----------------------
Workday career sites are single-page apps. The page you see in a browser is empty
HTML; the listings are fetched by the page's own JavaScript from a public JSON
endpoint on the same host. This module calls that same endpoint. It is public,
needs no login, and returns the same data the public page shows.

That is a lighter touch than scraping rendered HTML, but it is still automated
access, so this module is deliberately conservative:

  - it reads robots.txt first and refuses to proceed if the path is disallowed
  - it waits WORKDAY_DELAY_SECONDS between requests (minimum 1s, default 2s)
  - it stops after WORKDAY_MAX_PAGES
  - it sends a User-Agent that identifies what it is and who runs it
  - it gives up quietly on 403/429 rather than retrying harder

Before you run this regularly, read RMIT's terms of use and confirm you are
comfortable with it. If you would rather not, set ENABLE_WORKDAY=false and use
the site's own "create job alert" feature instead, which emails you new postings
and which this tracker can ingest through the Gmail source like any other alert.
"""

from __future__ import annotations

import logging
import time
import urllib.robotparser
from datetime import UTC, datetime, timedelta

import httpx
from dateutil import parser as date_parser

from tracker.config import get_settings
from tracker.ingest.base import PostingSource
from tracker.schemas import RawPosting

logger = logging.getLogger(__name__)

SOURCE_NAME = "rmit_careers"
HOST = "https://rmit.wd3.myworkdayjobs.com"
API_PATH = "/wday/cxs/rmit/RMIT_Careers/jobs"
PUBLIC_PATH = "/en-US/RMIT_Careers"
PAGE_SIZE = 20

USER_AGENT = (
    "rmit-job-mailer/1.0 (personal job alert tool for one RMIT student; "
    "contact via the GitHub repository)"
)

RELATIVE_POSTED = {
    "today": 0,
    "yesterday": 1,
}


def _robots_allows(url: str) -> bool:
    """Ask robots.txt before touching anything. Fail closed on doubt."""
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(f"{HOST}/robots.txt")
    try:
        parser.read()
    except Exception as exc:
        logger.warning("Could not read robots.txt (%s); not proceeding.", exc)
        return False
    allowed = parser.can_fetch(USER_AGENT, url)
    if not allowed:
        logger.warning("robots.txt disallows %s; skipping this source.", url)
    return allowed


def _parse_posted(value: str | None) -> datetime | None:
    """Workday returns things like 'Posted Today' or 'Posted 5 Days Ago'."""
    if not value:
        return None
    text = value.lower().replace("posted", "").strip()
    now = datetime.now(UTC)

    for word, days in RELATIVE_POSTED.items():
        if word in text:
            return now - timedelta(days=days)

    parts = text.split()
    if len(parts) >= 2 and parts[0].isdigit():
        count = int(parts[0])
        unit = parts[1].rstrip("s")
        if unit == "day":
            return now - timedelta(days=count)
        if unit == "week":
            return now - timedelta(weeks=count)
        if unit == "month":
            return now - timedelta(days=30 * count)

    try:
        return date_parser.parse(value, dayfirst=True, fuzzy=True)
    except (ValueError, OverflowError, TypeError):
        return None


def _location_of(item: dict) -> str | None:
    for key in ("locationsText", "primaryLocation", "location"):
        if value := item.get(key):
            return str(value).strip()
    return None


class WorkdaySource(PostingSource):
    name = SOURCE_NAME

    def __init__(self, search_text: str | None = None):
        settings = get_settings()
        self.search_text = search_text if search_text is not None else settings.workday_search_text
        self.delay = max(1.0, settings.workday_delay_seconds)
        self.max_pages = settings.workday_max_pages

    def fetch(self) -> list[RawPosting]:
        url = f"{HOST}{API_PATH}"
        if not _robots_allows(url):
            return []

        postings: list[RawPosting] = []
        seen_paths: set[str] = set()
        headers = {
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        with httpx.Client(timeout=30.0, headers=headers, follow_redirects=True) as client:
            for page in range(self.max_pages):
                offset = page * PAGE_SIZE
                payload = {
                    "appliedFacets": {},
                    "limit": PAGE_SIZE,
                    "offset": offset,
                    "searchText": self.search_text,
                }
                try:
                    response = client.post(url, json=payload)
                except httpx.HTTPError as exc:
                    logger.warning("RMIT Careers unreachable: %s", exc)
                    break

                if response.status_code in (403, 429):
                    logger.warning(
                        "RMIT Careers returned %s. Backing off and not retrying.",
                        response.status_code,
                    )
                    break
                if response.status_code >= 400:
                    logger.warning("RMIT Careers returned %s", response.status_code)
                    break

                try:
                    data = response.json()
                except ValueError:
                    logger.warning("RMIT Careers did not return JSON; the site may have changed.")
                    break

                items = data.get("jobPostings") or []
                if not items:
                    break

                for item in items:
                    path = item.get("externalPath") or ""
                    if path in seen_paths:
                        continue
                    seen_paths.add(path)

                    title = (item.get("title") or "").strip()
                    if not title:
                        continue

                    postings.append(
                        RawPosting(
                            title=title,
                            company="RMIT University",
                            location=_location_of(item),
                            url=f"{HOST}{PUBLIC_PATH}{path}" if path else None,
                            description=(item.get("jobDescription") or "").strip() or None,
                            source=SOURCE_NAME,
                            posted_at=_parse_posted(item.get("postedOn")),
                        )
                    )

                total = data.get("total")
                if total is not None and offset + PAGE_SIZE >= total:
                    break
                time.sleep(self.delay)

        logger.info("RMIT Careers returned %d postings", len(postings))
        return postings
