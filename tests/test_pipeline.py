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


# --- regressions found by the first live run against RMIT Careers ----------


def test_overseas_campus_roles_are_pushed_down():
    """RMIT has Vietnam campuses. Those jobs are unreachable from Melbourne.

    The first live run returned 40 postings, roughly half of them in Ho Chi Minh
    City or Hanoi, scoring the same as Melbourne roles because only interstate
    Australian cities carried a penalty.
    """
    melbourne = posting(title="Data Analyst", location="Melbourne VIC")
    saigon = posting(title="Data Analyst", location="Ho Chi Minh City")

    melbourne_score, _ = score(melbourne, classify(melbourne))
    saigon_score, reasons = score(saigon, classify(saigon))

    assert saigon_score < melbourne_score
    assert saigon_score == 0
    assert "overseas campus" in reasons


def test_academic_staff_roles_are_pushed_down():
    """A third year student cannot apply to be an Associate Professor.

    The live run ranked 'Associate Professor, Computing Technologies' second in
    the cybersecurity section: 'senior' was penalised but 'professor' was not.
    """
    job = posting(title="Associate Professor, Computing Technologies", location="Melbourne VIC")
    result, reasons = score(job, classify(job))
    assert result == 0
    assert "academic staff role" in reasons


def test_campus_category_needs_more_than_the_word_campus():
    """'Campus Security Specialist' is a staff job, not student work.

    The on-campus section is for casual student roles. Matching the bare word
    'campus' put three staff postings in it on the first live run.
    """
    assert classify(posting(title="Campus Security Specialist")) is not Category.CAMPUS
    assert classify(posting(title="Lecturer, Finance (Hanoi Campus)")) is not Category.CAMPUS
    assert classify(posting(title="Casual Student Services Assistant")) is Category.CAMPUS


def test_titles_with_non_breaking_spaces_are_cleaned(session):
    """Workday returned 'Associate Learning Designer\xa0-  (06 roles)'."""
    job, _ = upsert_posting(session, posting(title="Associate Learning\xa0Designer  -  (06 roles)"))
    assert job.title == "Associate Learning Designer - (06 roles)"


def test_student_facing_casual_roles_reach_the_campus_section():
    """'Global Experience Peer Advisor' is casual student work at RMIT Melbourne.

    It scored 0 and was filtered out of the digest on 24 September because the
    campus rules knew 'peer mentor' but not 'peer advisor'. These are the roles
    the on-campus section exists for, so a near-miss on wording is the one
    failure it cannot afford.
    """
    for title in [
        "Global Experience Peer Advisor",
        "Peer Support Leader",
        "Student Learning Adviser",
        "Exam Supervisor",
    ]:
        assert classify(posting(title=title)) is Category.CAMPUS, title


def test_widening_campus_rules_did_not_catch_staff_roles():
    """The previous fix pushed security and lecturer jobs out of on-campus.

    Widening the rules must not quietly undo that.
    """
    for title in [
        "Campus Security Specialist",
        "Student Communications Coordinator",
        "Lecturer, Finance (Hanoi Campus)",
        "Research Assistant, HAMR-TEI (Part-time, 04-month & Third-party Contract)",
    ]:
        assert classify(posting(title=title)) is not Category.CAMPUS, title


def test_a_melbourne_peer_advisor_clears_the_notification_threshold():
    """Classification alone is not enough; it has to survive NOTIFY_MIN_SCORE."""
    job = posting(title="Global Experience Peer Advisor", location="Melbourne")
    result, _ = score(job, classify(job))
    assert result >= 20
