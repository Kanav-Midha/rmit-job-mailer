"""The runner's contract: never email the same posting twice, never lose one."""

from __future__ import annotations

from tracker.config import get_settings
from tracker.ingest.base import PostingSource
from tracker.models import Job
from tracker.notify.mailer import MailError
from tracker.pipeline.runner import run
from tracker.schemas import RawPosting


class FakeSource(PostingSource):
    name = "fake"

    def __init__(self, postings):
        self.postings = postings

    def fetch(self):
        return list(self.postings)


class BrokenSource(PostingSource):
    name = "broken"

    def fetch(self):
        raise RuntimeError("upstream is down")


class RecordingMailer:
    channel = "recording"

    def __init__(self):
        self.batches = []

    def send(self, jobs):
        self.batches.append([j.title for j in jobs])


class FailingMailer:
    channel = "failing"

    def send(self, jobs):
        raise MailError("smtp refused")


def sample(n=2):
    return [
        RawPosting(title=f"Software Engineer {i}", company=f"Co {i}",
                   location="Melbourne VIC", source="fake")
        for i in range(n)
    ]


def test_new_postings_are_emailed_once(session):
    mailer = RecordingMailer()
    result = run([FakeSource(sample())], mailer)
    assert result.jobs_created == 2
    assert result.jobs_emailed == 2
    assert len(mailer.batches) == 1


def test_second_run_sends_nothing_new(session):
    postings = sample()
    mailer = RecordingMailer()
    run([FakeSource(postings)], mailer)
    second = run([FakeSource(postings)], mailer)
    assert second.jobs_created == 0
    assert second.jobs_emailed == 0
    assert len(mailer.batches) == 1


def test_only_the_new_posting_is_sent_the_second_time(session):
    mailer = RecordingMailer()
    run([FakeSource(sample(2))], mailer)
    run([FakeSource(sample(3))], mailer)
    assert mailer.batches[1] == ["Software Engineer 2"]


def test_a_failing_source_does_not_stop_the_others(session):
    mailer = RecordingMailer()
    result = run([BrokenSource(), FakeSource(sample(1))], mailer)
    assert result.jobs_created == 1
    assert result.errors and "upstream is down" in result.errors[0]


def test_send_failure_leaves_postings_pending_for_the_next_run(session):
    try:
        run([FakeSource(sample(2))], FailingMailer())
    except MailError:
        pass

    unsent = session.query(Job).filter(Job.emailed_at.is_(None)).count()
    assert unsent == 2

    mailer = RecordingMailer()
    result = run([FakeSource([])], mailer)
    assert result.jobs_emailed == 2


def test_dry_run_does_not_mark_anything_as_emailed(session):
    mailer = RecordingMailer()
    run([FakeSource(sample(2))], mailer, dry_run=True)
    assert session.query(Job).filter(Job.emailed_at.is_(None)).count() == 2


# --- "only the jobs I can actually apply to" -------------------------------


def student_and_staff():
    """One role a student can apply for, one they cannot."""
    return [
        RawPosting(title="Casual Library Assistant", company="RMIT University",
                   location="Melbourne", source="workday"),
        RawPosting(title="RMIT Council Member", company="RMIT University",
                   location="Melbourne", source="workday"),
    ]


def test_notify_categories_limits_the_digest_to_student_roles(session, monkeypatch):
    """RMIT posts mostly staff vacancies. A student wants the campus section only.

    A score threshold only approximates that: a new professional role could score
    above the line and slip in. Naming the category says it exactly.
    """
    monkeypatch.setenv("NOTIFY_CATEGORIES", "campus")
    get_settings.cache_clear()

    mailer = RecordingMailer()
    run([FakeSource(student_and_staff())], mailer)

    get_settings.cache_clear()
    assert mailer.batches == [["Casual Library Assistant"]]


def test_an_empty_category_list_means_everything(session, monkeypatch):
    monkeypatch.setenv("NOTIFY_CATEGORIES", "")
    monkeypatch.setenv("NOTIFY_MIN_SCORE", "0")
    get_settings.cache_clear()

    mailer = RecordingMailer()
    run([FakeSource(student_and_staff())], mailer)

    get_settings.cache_clear()
    assert sorted(mailer.batches[0]) == ["Casual Library Assistant", "RMIT Council Member"]


def test_a_filtered_posting_is_not_marked_sent(session, monkeypatch):
    """Widening the categories later must deliver the backlog, not lose it."""
    monkeypatch.setenv("NOTIFY_CATEGORIES", "campus")
    get_settings.cache_clear()
    run([FakeSource(student_and_staff())], RecordingMailer())

    monkeypatch.setenv("NOTIFY_CATEGORIES", "")
    monkeypatch.setenv("NOTIFY_MIN_SCORE", "0")
    get_settings.cache_clear()

    mailer = RecordingMailer()
    run([], mailer)
    get_settings.cache_clear()

    assert mailer.batches == [["RMIT Council Member"]]
