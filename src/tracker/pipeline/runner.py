"""One full run: fetch every source, store what is new, email a single digest.

Order matters. The digest is sent first, and only then are the jobs marked as
emailed. If sending fails, nothing is marked, so the next run retries them rather
than silently dropping postings you never saw.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from tracker.config import get_settings
from tracker.db import session_scope
from tracker.ingest.base import MessageSource, PostingSource
from tracker.ingest.parsers.registry import parse_message
from tracker.models import Category, Job, utcnow
from tracker.pipeline.normalise import upsert_posting
from tracker.schemas import RawPosting, RunResult

logger = logging.getLogger(__name__)


def collect(sources: list, result: RunResult) -> list[RawPosting]:
    """Fetch from every source. One failing source must not stop the others."""
    postings: list[RawPosting] = []

    for source in sources:
        try:
            if isinstance(source, PostingSource):
                found = source.fetch()
                postings.extend(found)
                result.postings_parsed += len(found)

            elif isinstance(source, MessageSource):
                messages = source.fetch()
                result.messages_fetched += len(messages)
                for message in messages:
                    try:
                        parsed = parse_message(message)
                    except Exception as exc:
                        logger.error("Parsing message %s failed: %s", message.message_id, exc)
                        result.errors.append(f"parse {message.message_id}: {exc}")
                        continue
                    postings.extend(parsed)
                    result.postings_parsed += len(parsed)
            else:
                logger.warning("Unknown source type: %r", source)

        except Exception as exc:
            logger.error("Source %s failed: %s", getattr(source, "name", source), exc)
            result.errors.append(f"{getattr(source, 'name', source)}: {exc}")

    return postings


def run(sources: list, mailer, dry_run: bool = False) -> RunResult:
    settings = get_settings()
    result = RunResult()

    postings = collect(sources, result)

    with session_scope() as session:
        for posting in postings:
            try:
                _, created = upsert_posting(session, posting)
            except Exception as exc:
                logger.error("Storing %r failed: %s", posting.title, exc)
                result.errors.append(f"store {posting.title[:40]}: {exc}")
                continue
            if created:
                result.jobs_created += 1
            else:
                result.jobs_updated += 1

    # Everything never emailed, above the threshold. Includes anything a previous
    # run collected but failed to send.
    with session_scope() as session:
        query = select(Job).where(
            Job.emailed_at.is_(None), Job.score >= settings.notify_min_score
        )

        # A posting filtered out here keeps emailed_at NULL, so widening the
        # categories later sends the backlog rather than silently losing it.
        wanted = settings.notify_category_list
        if wanted:
            query = query.where(Job.category.in_([Category(c) for c in wanted]))

        pending = list(
            session.scalars(
                query.order_by(Job.score.desc(), Job.first_seen_at.desc()).limit(
                    settings.notify_max_per_run
                )
            ).all()
        )

        if not pending:
            logger.info("Nothing new to send.")
            return result

        mailer.send(pending)
        result.jobs_emailed = len(pending)
        result.email_sent = not dry_run

        if not dry_run:
            stamp = utcnow()
            for job in pending:
                session.merge(job).emailed_at = stamp

    return result
