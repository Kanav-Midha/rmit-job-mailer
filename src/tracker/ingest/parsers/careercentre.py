"""Parser for rmit.careercentre.me saved-search alert emails.

IMPORTANT - read before trusting this:
These emails have no published schema and their markup changes without notice. The
heuristics below target the general shape (a list of postings, each an anchor to a
job page, with employer and location in nearby text) and are tested against the
synthetic fixtures in tests/fixtures/emails/.

Your first real task: save one genuine alert email, redact your address and any
recruiter contact details, drop it in tests/fixtures/emails/, and tune until the
tests pass against it.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup, Tag
from dateutil import parser as date_parser

from tracker.ingest.base import RawMessage
from tracker.schemas import RawPosting

logger = logging.getLogger(__name__)
SOURCE_NAME = "rmit_careercentre"

JOB_URL_PATTERNS = [
    re.compile(r"careercentre\.me", re.I),
    re.compile(r"/job[s]?/", re.I),
    re.compile(r"[?&]jobid=", re.I),
    re.compile(r"/vacanc", re.I),
]

NOISE_TEXT = re.compile(
    r"^(unsubscribe|view (in|online)|manage .*preferences|privacy|contact us|"
    r"log ?in|sign ?in|update your details|click here|home|more jobs?)$",
    re.I,
)

LABELLED_FIELD = re.compile(
    r"(?P<label>company|employer|organisation|organization|location|based in|closes|"
    r"closing date|applications close|posted|date posted)\s*[:\-]\s*(?P<value>[^\n|]+)",
    re.I,
)

LOCATION_HINT = re.compile(
    r"\b(melbourne|sydney|brisbane|perth|adelaide|canberra|hobart|darwin|geelong|"
    r"remote|hybrid|on[- ]?campus|vic|nsw|qld|wa|sa|act|tas|nt|australia)\b",
    re.I,
)


def _clean(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"\s+", " ", value).strip(" \t\r\n:-|\u00a0")
    return text or None


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return date_parser.parse(value, dayfirst=True, fuzzy=True)
    except (ValueError, OverflowError, TypeError):
        return None


def _is_job_link(href: str, text: str) -> bool:
    if not href or not text or len(text.strip()) < 4:
        return False
    if NOISE_TEXT.match(text.strip()):
        return False
    return any(pattern.search(href) for pattern in JOB_URL_PATTERNS)


def _block_for(anchor: Tag) -> Tag:
    node = anchor
    for _ in range(4):
        parent = node.parent
        if parent is None or parent.name in {"body", "html", "[document]"}:
            break
        node = parent
        if node.name in {"td", "tr", "li", "table", "div"} and len(node.get_text(strip=True)) > 40:
            break
    return node


def _extract_fields(block_text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for match in LABELLED_FIELD.finditer(block_text):
        label = match.group("label").lower()
        value = _clean(match.group("value"))
        if not value:
            continue
        if label in {"company", "employer", "organisation", "organization"}:
            found.setdefault("company", value)
        elif label in {"location", "based in"}:
            found.setdefault("location", value)
        elif label in {"closes", "closing date", "applications close"}:
            found.setdefault("closes", value)
        elif label in {"posted", "date posted"}:
            found.setdefault("posted", value)
    return found


def _fallback_location(block_text: str) -> str | None:
    for line in block_text.splitlines():
        line = line.strip()
        if 3 < len(line) < 80 and LOCATION_HINT.search(line):
            return _clean(line)
    return None


def parse(message: RawMessage) -> list[RawPosting]:
    body = message.body
    if not body:
        return []

    soup = BeautifulSoup(body, "lxml")
    postings: list[RawPosting] = []
    seen_urls: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        title = _clean(anchor.get_text(" ", strip=True))
        if not title or not _is_job_link(href, title) or href in seen_urls:
            continue
        seen_urls.add(href)

        block_text = _block_for(anchor).get_text("\n", strip=True)
        fields = _extract_fields(block_text)

        postings.append(
            RawPosting(
                title=title,
                company=fields.get("company"),
                location=fields.get("location") or _fallback_location(block_text),
                url=href,
                description=block_text[:2000] or None,
                source=SOURCE_NAME,
                posted_at=_parse_date(fields.get("posted")) or message.received_at,
                closes_at=_parse_date(fields.get("closes")),
            )
        )

    if not postings:
        logger.info(
            "No postings found in message %s (subject=%r). If it did contain jobs, "
            "the parser needs tuning.",
            message.message_id,
            message.subject,
        )
    return postings
