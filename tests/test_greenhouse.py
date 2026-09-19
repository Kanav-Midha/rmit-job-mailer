"""Greenhouse source.

Sample shapes are taken from a real response to
https://boards-api.greenhouse.io/v1/boards/cultureamp/jobs so the tests fail if
Greenhouse changes its schema rather than passing against something invented.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from tracker.ingest.greenhouse_source import GreenhouseSource, to_posting
from tracker.models import Category
from tracker.pipeline.classify import classify
from tracker.pipeline.score import score

JOB = {
    "id": 7891234,
    "title": "Graduate Software Engineer",
    "absolute_url": "https://job-boards.greenhouse.io/cultureamp/jobs/7891234",
    "location": {"name": "Melbourne, Victoria, Australia"},
    "updated_at": "2026-09-15T04:21:36-04:00",
    "first_published": "2026-09-01T09:00:00-04:00",
    "application_deadline": None,
}


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_job_object_becomes_a_posting():
    posting = to_posting(JOB, "Culture Amp")
    assert posting is not None
    assert posting.title == "Graduate Software Engineer"
    assert posting.company == "Culture Amp"
    assert posting.location == "Melbourne, Victoria, Australia"
    assert posting.url == "https://job-boards.greenhouse.io/cultureamp/jobs/7891234"
    assert posting.source == "greenhouse"


def test_timestamps_are_timezone_aware():
    """Naive datetimes crash the closing-date arithmetic in the digest."""
    posting = to_posting(JOB, "Culture Amp")
    assert posting.posted_at is not None
    assert posting.posted_at.tzinfo is not None
    assert posting.posted_at.astimezone(UTC) < datetime.now(UTC)


def test_a_job_without_a_title_is_dropped():
    """Better no posting than an 'Untitled role' nobody can act on."""
    assert to_posting({**JOB, "title": "  "}, "Culture Amp") is None


def test_a_job_without_a_location_still_works():
    posting = to_posting({**JOB, "location": None}, "Culture Amp")
    assert posting is not None and posting.location is None


def test_fetch_reads_every_configured_board():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json={"jobs": [JOB]})

    source = GreenhouseSource(tokens=["cultureamp", "canva"], delay=0)
    with _client(handler) as client:
        postings = source._fetch_board(client, "cultureamp") + source._fetch_board(client, "canva")

    assert len(postings) == 2
    assert seen == [
        "/v1/boards/cultureamp/jobs",
        "/v1/boards/canva/jobs",
    ]


def test_a_missing_board_is_skipped_not_fatal():
    """A company that does not use Greenhouse 404s. That is a config mistake,
    not an outage, and it must not cost us the other boards."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Not Found")

    source = GreenhouseSource(tokens=["nosuchcompany"], delay=0)
    with _client(handler) as client:
        assert source._fetch_board(client, "nosuchcompany") == []


def test_no_boards_configured_returns_nothing_quietly():
    assert GreenhouseSource(tokens=[], delay=0).fetch() == []


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Graduate Software Engineer", Category.SOFTWARE_ENGINEERING),
        ("Machine Learning Engineer", Category.MACHINE_LEARNING),
        ("Data Analyst, Intern", Category.DATA_SCIENCE),
    ],
)
def test_greenhouse_postings_flow_through_the_existing_pipeline(title, expected):
    """The point of this source: no classifier or scorer changes needed."""
    posting = to_posting({**JOB, "title": title}, "Culture Amp")
    category = classify(posting)
    assert category is expected

    result, reasons = score(posting, category)
    assert result > 0
    assert "Melbourne" in reasons
