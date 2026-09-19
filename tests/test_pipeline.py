from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tracker.models import Category
from tracker.pipeline.classify import classify
from tracker.pipeline.dedupe import content_hash, normalise_text, titles_match
from tracker.pipeline.normalise import upsert_posting
from tracker.pipeline.score import score
from tracker.schemas import RawPosting


def posting(**kw) -> RawPosting:
    base = dict(
        title="Software Engineer Intern",
        company="Northbound Systems",
        location="Melbourne VIC",
        source="rmit_careercentre",
    )
    base.update(kw)
    return RawPosting(**base)


def test_hash_ignores_case_and_punctuation():
    assert content_hash(posting()) == content_hash(
        posting(title="software engineer intern!", company="Northbound  Systems")
    )


def test_hash_ignores_tracking_parameters():
    assert content_hash(posting(url="https://x/j?id=1")) == content_hash(
        posting(url="https://x/j?id=1&utm_source=email")
    )


def test_normalise_strips_filler():
    assert normalise_text("The Software Engineer Role (m/f/d)") == "software engineer"


def test_fuzzy_titles_match_across_rewordings():
    assert titles_match("Software Engineer Intern", "Software Engineering Intern")
    assert not titles_match("Software Engineer", "Security Analyst")


def test_same_posting_twice_creates_one_row(session):
    a, created_a = upsert_posting(session, posting())
    b, created_b = upsert_posting(session, posting())
    assert created_a and not created_b and a.id == b.id


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Software Engineer Intern", Category.SOFTWARE_ENGINEERING),
        ("Machine Learning Engineer", Category.MACHINE_LEARNING),
        ("Data Scientist", Category.DATA_SCIENCE),
        ("Penetration Tester", Category.CYBERSECURITY),
        ("Student Ambassador", Category.CAMPUS),
        ("Barista", Category.OTHER),
    ],
)
def test_classification(title, expected):
    assert classify(RawPosting(title=title, source="t")) is expected


def test_melbourne_internship_scores_well():
    value, _ = score(
        posting(description="Penultimate year. Python and Java."),
        Category.SOFTWARE_ENGINEERING,
    )
    assert value >= 70


def test_senior_interstate_clearance_role_scores_poorly():
    value, _ = score(
        posting(
            title="Senior Security Engineer",
            location="Sydney NSW",
            description="8+ years experience. Australian citizenship required. NV1 clearance.",
        ),
        Category.CYBERSECURITY,
    )
    assert value <= 25


def test_closing_soon_ranks_higher():
    soon = datetime.now(UTC) + timedelta(days=2)
    later = datetime.now(UTC) + timedelta(days=60)
    assert (
        score(posting(closes_at=soon), Category.SOFTWARE_ENGINEERING)[0]
        > score(posting(closes_at=later), Category.SOFTWARE_ENGINEERING)[0]
    )
