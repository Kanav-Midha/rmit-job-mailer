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


# --- regressions from the first live Gmail run -----------------------------

SAFELINK = (
    "https://aus01.safelinks.protection.outlook.com/?url=https%3A%2F%2Frmit."
    "careercentre.me%2Fu%2F25fcn3nt&data=05%7C02%7Cakbar.staffmember%40rmit.edu.au"
    "%7C0e0c3bdfb0b3429354ad08df0a2da723&reserved=0"
)


def test_safelink_is_unwrapped_to_the_real_url():
    """RMIT sends through Microsoft 365, which rewrites every link.

    The wrapper is ~600 characters and carries the sending staff member's email
    address. The first live run stored both in the database and put them in the
    digest.
    """
    from tracker.ingest.parsers.careercentre import unwrap_safelink

    assert unwrap_safelink(SAFELINK) == "https://rmit.careercentre.me/u/25fcn3nt"


def test_unwrapping_removes_the_staff_email_address():
    from tracker.ingest.parsers.careercentre import unwrap_safelink

    assert "rmit.edu.au" not in unwrap_safelink(SAFELINK)


def test_ordinary_urls_pass_through_unchanged():
    from tracker.ingest.parsers.careercentre import unwrap_safelink

    plain = "https://rmit.careercentre.me/u/4urccuok"
    assert unwrap_safelink(plain) == plain


def test_an_anchor_showing_a_bare_url_is_not_a_job():
    """The first live run produced postings titled 'https://rmit.careercentre.me/u/...'.

    When an email prints the link instead of linking a title, there is no title
    to take, and a URL as a job title is worse than no posting at all.
    """
    from tracker.ingest.parsers.careercentre import _is_job_link

    url = "https://rmit.careercentre.me/u/4urccuok"
    assert not _is_job_link(url, url)
    assert not _is_job_link(url, "www.rmit.careercentre.me/u/4urccuok")
    assert _is_job_link(url, "Graduate Software Engineer")
