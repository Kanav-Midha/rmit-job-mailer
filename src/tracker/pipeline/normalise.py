"""Turns postings into stored Jobs: dedupe, classify, score, persist."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from tracker.models import Job, utcnow
from tracker.pipeline.classify import classify
from tracker.pipeline.dedupe import content_hash, find_existing
from tracker.pipeline.score import score
from tracker.schemas import RawPosting

logger = logging.getLogger(__name__)
MAX_TITLE, MAX_SHORT = 300, 200


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value[:limit] if value else None


def upsert_posting(session: Session, posting: RawPosting) -> tuple[Job, bool]:
    """Store a posting. Returns (job, created); created is False for a repeat sighting."""
    if existing := find_existing(session, posting):
        existing.last_seen_at = utcnow()
        existing.is_active = True
        if not existing.url and posting.url:
            existing.url = posting.url
        if not existing.location and posting.location:
            existing.location = _truncate(posting.location, MAX_SHORT)
        if not existing.closes_at and posting.closes_at:
            existing.closes_at = posting.closes_at
        session.flush()
        return existing, False

    category = classify(posting)
    relevance, reasons = score(posting, category)

    job = Job(
        content_hash=content_hash(posting),
        title=_truncate(posting.title, MAX_TITLE) or "Untitled role",
        company=_truncate(posting.company, MAX_SHORT),
        location=_truncate(posting.location, MAX_SHORT),
        url=posting.url,
        description=posting.description,
        source=posting.source,
        posted_at=posting.posted_at,
        closes_at=posting.closes_at,
        category=category,
        score=relevance,
        score_reasons=reasons,
    )
    session.add(job)
    session.flush()
    logger.info("New job #%s %r (%s, score %s)", job.id, job.title, category.value, relevance)
    return job, True
