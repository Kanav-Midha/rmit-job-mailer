"""Deduplication.

Two layers, because alert emails repeat postings across days and boards reword titles:

1. content_hash - exact match on normalised (title, employer, location).
2. fuzzy match  - near-identical titles at the same employer, for when a board
   changes "Software Engineer Intern" to "Software Engineering Intern".
"""

from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from tracker.models import Job
from tracker.schemas import RawPosting

FUZZY_THRESHOLD = 0.92

_PUNCT = re.compile(r"[^a-z0-9 ]+")
_SPACE = re.compile(r"\s+")
_FILLER = re.compile(r"\b(the|a|an|role|position|opportunity|vacancy|job|f|m|x|d|new|hiring)\b")


def normalise_text(value: str | None) -> str:
    if not value:
        return ""
    text = _PUNCT.sub(" ", value.lower())
    text = _FILLER.sub(" ", text)
    return _SPACE.sub(" ", text).strip()


def content_hash(posting: RawPosting) -> str:
    """Stable identity. Excludes the URL, because the same job arrives with
    different tracking parameters on different days."""
    parts = [
        normalise_text(posting.title),
        normalise_text(posting.company),
        normalise_text(posting.location),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def titles_match(left: str, right: str, threshold: float = FUZZY_THRESHOLD) -> bool:
    a, b = normalise_text(left), normalise_text(right)
    if not a or not b:
        return False
    return a == b or SequenceMatcher(None, a, b).ratio() >= threshold


def find_existing(session: Session, posting: RawPosting) -> Job | None:
    """Return the stored Job this posting duplicates, or None if it is new.

    Known limitation: a posting first seen without an employer cannot later be merged
    with the same posting seen with one, because employer is part of the identity.
    That is deliberate - guessing would merge genuinely different jobs sharing a title,
    which is a worse failure than an occasional duplicate row.
    """
    digest = content_hash(posting)
    if exact := session.scalar(select(Job).where(Job.content_hash == digest)):
        return exact

    company_key = normalise_text(posting.company)
    if not company_key:
        return None

    for candidate in session.scalars(select(Job).where(Job.source == posting.source)).all():
        if normalise_text(candidate.company) == company_key and titles_match(
            candidate.title, posting.title
        ):
            return candidate
    return None
