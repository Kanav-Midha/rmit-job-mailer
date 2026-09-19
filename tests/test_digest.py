"""The digest is the product, so it gets tested like one."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tracker.models import Category, Job
from tracker.notify.digest import build_html, build_text, subject_line


def job(**kw) -> Job:
    base = dict(
        id=1,
        content_hash="h",
        title="Software Engineer Intern",
        company="Northbound Systems",
        location="Melbourne VIC",
        url="https://example.com/jobs/1",
        source="test",
        category=Category.SOFTWARE_ENGINEERING,
        score=88,
    )
    base.update(kw)
    return Job(**base)


def test_subject_names_the_top_match_when_several():
    jobs = [job(), job(id=2, title="Student Ambassador", score=40, category=Category.CAMPUS)]
    subject = subject_line(jobs)
    assert "2 new" in subject and "Software Engineer Intern" in subject


def test_subject_is_singular_for_one_posting():
    assert subject_line([job()]).startswith("1 new")


def test_text_digest_contains_score_title_and_link():
    body = build_text([job()])
    assert "Software Engineer Intern" in body
    assert "https://example.com/jobs/1" in body
    assert "88" in body


def test_sections_are_grouped_by_category():
    jobs = [job(), job(id=2, title="Student Ambassador", score=40, category=Category.CAMPUS)]
    body = build_text(jobs)
    assert "SOFTWARE ENGINEERING" in body
    assert "ON CAMPUS AT RMIT" in body
    # Software engineering outranks campus, so its section comes first.
    assert body.index("SOFTWARE ENGINEERING") < body.index("ON CAMPUS AT RMIT")


def test_higher_scores_come_first_within_a_section():
    low = job(id=1, title="Low match", score=20)
    high = job(id=2, title="High match", score=90)
    body = build_text([low, high])
    assert body.index("High match") < body.index("Low match")


def test_html_escapes_hostile_content():
    body = build_html([job(title='Dev <script>alert("x")</script>')])
    assert "<script>" not in body
    assert "&lt;script&gt;" in body


def test_closing_soon_is_flagged():
    soon = datetime.now(UTC) + timedelta(days=2)
    assert "closes in 2 days" in build_text([job(closes_at=soon)])


def test_missing_optional_fields_do_not_break_rendering():
    bare = job(company=None, location=None, url=None, closes_at=None, description=None)
    assert "Software Engineer Intern" in build_text([bare])
    assert "Software Engineer Intern" in build_html([bare])


@pytest.mark.parametrize("builder", [build_text, build_html])
def test_builders_handle_a_realistic_mix(builder):
    jobs = [
        job(),
        job(id=2, title="Student Ambassador", category=Category.CAMPUS, score=64),
        job(id=3, title="Data Scientist", category=Category.DATA_SCIENCE, score=70),
    ]
    assert len(builder(jobs)) > 100
