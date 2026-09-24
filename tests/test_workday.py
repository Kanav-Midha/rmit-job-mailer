"""RMIT Careers pagination and country filtering.

Written after a live run on 24 September collected 40 postings while RMIT's own
API reported 51. Eleven roles were never seen. For a tool whose whole promise is
"you will not miss a job", that is the only bug class that really matters.
"""

from __future__ import annotations

import httpx
import pytest

from tracker.ingest.base import SourceUnavailable
from tracker.ingest.workday_source import AUSTRALIA, COUNTRY_FACET, PAGE_SIZE, WorkdaySource


def page(n: int, count: int, total: int) -> dict:
    return {
        "total": total,
        "jobPostings": [
            {
                "title": f"Role {n}-{i}",
                "externalPath": f"/job/Melbourne/Role-{n}-{i}_JR{n}{i}",
                "locationsText": "Melbourne",
                "postedOn": "Posted Today",
            }
            for i in range(count)
        ],
    }


@pytest.fixture
def source(monkeypatch):
    monkeypatch.setattr("tracker.ingest.workday_source._robots_allows", lambda url: True)
    monkeypatch.setattr("tracker.ingest.workday_source.time.sleep", lambda s: None)
    return WorkdaySource()


def mock_pages(monkeypatch, pages: list[dict], seen: list | None = None):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            import json

            seen.append(json.loads(request.content))
        body = pages[min(calls["n"], len(pages) - 1)]
        calls["n"] += 1
        return httpx.Response(200, json=body)

    real_client = httpx.Client

    def fake_client(*a, **kw):
        kw["transport"] = httpx.MockTransport(handler)
        return real_client(*a, **kw)

    monkeypatch.setattr("tracker.ingest.workday_source.httpx.Client", fake_client)
    return calls


def test_pagination_does_not_stop_early_on_a_misleading_total(source, monkeypatch):
    """The live bug: page two reported a total relative to its own offset.

    Three full pages then a short one must yield every posting, whatever `total`
    claims along the way.
    """
    mock_pages(
        monkeypatch,
        [
            page(0, PAGE_SIZE, 51),
            page(1, PAGE_SIZE, 31),  # the value that used to end the loop
            page(2, 11, 11),
        ],
    )
    assert len(source.fetch()) == 51


def test_a_short_page_ends_the_loop(source, monkeypatch):
    calls = mock_pages(monkeypatch, [page(0, 7, 7)])
    assert len(source.fetch()) == 7
    assert calls["n"] == 1


def test_australia_is_requested_from_the_api(source, monkeypatch):
    """37 of RMIT's 51 postings are at its Vietnam campuses and cannot be applied
    for from Melbourne. Filtering server-side is exact; guessing from city names
    would break on a campus we had not heard of."""
    seen: list[dict] = []
    mock_pages(monkeypatch, [page(0, 3, 3)], seen=seen)
    source.fetch()
    assert seen[0]["appliedFacets"] == {COUNTRY_FACET: [AUSTRALIA]}


def test_a_blank_country_fetches_everything(monkeypatch):
    monkeypatch.setenv("WORKDAY_COUNTRY_FACET", "")
    from tracker.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr("tracker.ingest.workday_source._robots_allows", lambda url: True)
    monkeypatch.setattr("tracker.ingest.workday_source.time.sleep", lambda s: None)

    seen: list[dict] = []
    mock_pages(monkeypatch, [page(0, 2, 2)], seen=seen)
    WorkdaySource().fetch()
    get_settings.cache_clear()

    assert seen[0]["appliedFacets"] == {}


def test_hitting_the_page_cap_is_logged_not_silent(source, monkeypatch, caplog):
    """Truncation must be loud. A silent cap is how 11 jobs went missing."""
    source.max_pages = 2
    mock_pages(monkeypatch, [page(0, PAGE_SIZE, 999), page(1, PAGE_SIZE, 999)])
    with caplog.at_level("WARNING"):
        source.fetch()
    assert any("WORKDAY_MAX_PAGES" in r.getMessage() for r in caplog.records)


def test_a_shortfall_against_the_reported_total_is_logged(source, monkeypatch, caplog):
    source.max_pages = 1
    mock_pages(monkeypatch, [page(0, PAGE_SIZE, 51)])
    with caplog.at_level("WARNING"):
        source.fetch()
    assert any("only 20 were collected" in r.getMessage() for r in caplog.records)


# --- an empty result must not be mistaken for a quiet day ---------------------
#
# Every silent failure ends the same way: fetch() returns nothing, the run exits
# green, no digest is sent. From the inbox that is identical to RMIT having
# posted nothing overnight, which is the one failure nobody would ever notice.
# RMIT always advertises a dozen or so Australian roles, so zero is a bug.


def test_an_empty_response_raises_rather_than_returning_nothing(source, monkeypatch):
    mock_pages(monkeypatch, [{"total": 0, "jobPostings": []}])
    with pytest.raises(SourceUnavailable, match="expected at least"):
        source.fetch()


def test_a_blocked_request_raises(source, monkeypatch):
    """403 and 429 break out of the loop with nothing collected."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="Forbidden")

    real_client = httpx.Client
    monkeypatch.setattr(
        "tracker.ingest.workday_source.httpx.Client",
        lambda *a, **kw: real_client(*a, **{**kw, "transport": httpx.MockTransport(handler)}),
    )
    with pytest.raises(SourceUnavailable):
        source.fetch()


def test_a_robots_refusal_raises_and_says_what_to_do(monkeypatch):
    """The case that prompted all of this: robots.txt unreachable or disallowing
    returns an empty list before a single request is made."""
    monkeypatch.setattr("tracker.ingest.workday_source._robots_allows", lambda url: False)
    with pytest.raises(SourceUnavailable, match="robots.txt"):
        WorkdaySource().fetch()


def test_the_check_can_be_switched_off(monkeypatch):
    """A fork pointing at a country with no vacancies needs to allow an empty run."""
    monkeypatch.setenv("WORKDAY_MIN_EXPECTED", "0")
    from tracker.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr("tracker.ingest.workday_source._robots_allows", lambda url: False)
    try:
        assert WorkdaySource().fetch() == []
    finally:
        get_settings.cache_clear()


def test_one_posting_is_enough_to_pass(source, monkeypatch):
    """The guard catches zero, not a genuinely thin day."""
    mock_pages(monkeypatch, [page(0, 1, 1)])
    assert len(source.fetch()) == 1
