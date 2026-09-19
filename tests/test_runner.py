"""The runner's contract: never email the same posting twice, never lose one."""

from __future__ import annotations

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
