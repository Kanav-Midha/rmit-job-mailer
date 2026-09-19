from __future__ import annotations

from tracker.ingest.parsers import careercentre


def test_parses_every_posting_in_a_digest(swe_message):
    postings = careercentre.parse(swe_message)
    assert len(postings) == 3


def test_extracts_labelled_fields(swe_message):
    intern = next(p for p in careercentre.parse(swe_message) if "Intern" in p.title)
    assert intern.company == "Northbound Systems"
    assert intern.location == "Melbourne VIC"
    assert intern.closes_at is not None
    assert intern.url.endswith("jobid=100001")


def test_ignores_unsubscribe_and_preferences_links(swe_message):
    urls = [p.url for p in careercentre.parse(swe_message)]
    assert not any("unsubscribe" in u or "preferences" in u for u in urls)


def test_digest_with_no_jobs_yields_nothing(empty_message):
    assert careercentre.parse(empty_message) == []
