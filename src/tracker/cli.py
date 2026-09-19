"""Command line entry point.

  python -m tracker.cli init-db          create tables
  python -m tracker.cli auth             one-off Gmail consent
  python -m tracker.cli check            verify config without sending
  python -m tracker.cli run --dry-run    print the digest instead of sending
  python -m tracker.cli run              collect and email
  python -m tracker.cli test-email       send yourself a sample to check formatting
  python -m tracker.cli list             show what is stored
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC

from sqlalchemy import func, select

from tracker.config import get_settings
from tracker.db import init_db, session_scope
from tracker.models import Job

logger = logging.getLogger(__name__)


def _build_sources(args) -> list:
    sources = []
    settings = get_settings()

    if not args.no_gmail:
        try:
            from tracker.ingest.gmail_source import GmailSource

            sources.append(GmailSource())
        except Exception as exc:
            print(f"Gmail source unavailable: {exc}", file=sys.stderr)

    if settings.enable_workday and not args.no_workday:
        from tracker.ingest.workday_source import WorkdaySource

        sources.append(WorkdaySource())

    return sources


def cmd_init_db(_args) -> int:
    init_db()
    print(f"Tables ready in {get_settings().database_url}")
    return 0


def cmd_auth(_args) -> int:
    from tracker.ingest.gmail_source import authorise

    authorise()
    print("Gmail authorised. token.json written (and gitignored).")
    return 0


def cmd_check(_args) -> int:
    """Tell the user exactly what is and is not configured, without sending anything."""
    s = get_settings()
    from pathlib import Path

    rows = [
        ("Database", s.database_url, True),
        ("Send to", s.mail_to or "not set", bool(s.mail_to)),
        ("SMTP host", f"{s.smtp_host}:{s.smtp_port}", bool(s.smtp_host)),
        ("SMTP user", s.smtp_username or "not set", bool(s.smtp_username)),
        ("SMTP password", "set" if s.smtp_password else "not set", bool(s.smtp_password)),
        (
            "Gmail token",
            s.gmail_token_file,
            Path(s.gmail_token_file).exists(),
        ),
        ("RMIT Careers", "enabled" if s.enable_workday else "disabled", True),
        ("Min score to email", str(s.notify_min_score), True),
    ]
    width = max(len(name) for name, _, _ in rows)
    for name, value, ok in rows:
        print(f"  {'ok ' if ok else '-- '} {name.ljust(width)}  {value}")

    if not s.smtp_configured:
        print("\nEmail is not configured yet. Fill in MAIL_TO, SMTP_USERNAME and "
              "SMTP_PASSWORD in .env.", file=sys.stderr)
        return 1
    return 0


def cmd_run(args) -> int:
    from tracker.notify.mailer import ConsolePrinter, DigestMailer, MailError
    from tracker.pipeline.runner import run

    init_db()

    if args.dry_run:
        mailer = ConsolePrinter()
    else:
        try:
            mailer = DigestMailer()
        except MailError as exc:
            print(f"{exc}\nRun with --dry-run to test without sending.", file=sys.stderr)
            return 1

    try:
        result = run(_build_sources(args), mailer, dry_run=args.dry_run)
    except MailError as exc:
        print(f"{exc}", file=sys.stderr)
        return 1

    print(
        f"\nmessages={result.messages_fetched} postings={result.postings_parsed} "
        f"new={result.jobs_created} seen_again={result.jobs_updated} "
        f"emailed={result.jobs_emailed}"
    )
    for error in result.errors:
        print(f"  warning: {error}", file=sys.stderr)
    return 0


def cmd_test_email(_args) -> int:
    """Send a sample digest so you can check it renders before trusting the schedule."""
    from datetime import datetime, timedelta

    from tracker.models import Category
    from tracker.notify.mailer import DigestMailer, MailError

    samples = [
        Job(
            id=1,
            content_hash="sample1",
            title="Software Engineer Intern",
            company="Northbound Systems",
            location="Melbourne VIC",
            url="https://example.com/jobs/1",
            description="Penultimate year students. Python, Java, REST APIs.",
            source="sample",
            category=Category.SOFTWARE_ENGINEERING,
            score=88,
            closes_at=datetime.now(UTC) + timedelta(days=3),
        ),
        Job(
            id=2,
            content_hash="sample2",
            title="Student Ambassador",
            company="RMIT University",
            location="RMIT City Campus, Melbourne",
            url="https://example.com/jobs/2",
            source="sample",
            category=Category.CAMPUS,
            score=64,
        ),
    ]
    try:
        DigestMailer().send(samples)
    except MailError as exc:
        print(f"{exc}", file=sys.stderr)
        return 1
    print(f"Sample digest sent to {get_settings().mail_to}. Check it renders properly.")
    return 0


def cmd_list(args) -> int:
    with session_scope() as session:
        total = session.scalar(select(func.count(Job.id))) or 0
        jobs = session.scalars(
            select(Job)
            .where(Job.score >= args.min_score)
            .order_by(Job.score.desc(), Job.first_seen_at.desc())
            .limit(args.limit)
        ).all()

        if not jobs:
            print("Nothing stored yet. Run: python -m tracker.cli run --dry-run")
            return 0

        print(f"{total} postings stored. Showing {len(jobs)}.\n")
        for job in jobs:
            sent = "emailed" if job.emailed_at else "pending"
            print(f"[{job.score:3d}] {job.title}  -  {job.company or 'unknown'}  ({sent})")
            if job.url:
                print(f"       {job.url}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tracker", description="RMIT job mailer")
    parser.add_argument("--log-level", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="create database tables").set_defaults(func=cmd_init_db)
    sub.add_parser("auth", help="authorise Gmail access").set_defaults(func=cmd_auth)
    sub.add_parser("check", help="show what is configured").set_defaults(func=cmd_check)
    sub.add_parser("test-email", help="send a sample digest").set_defaults(func=cmd_test_email)

    run_cmd = sub.add_parser("run", help="collect postings and email the digest")
    run_cmd.add_argument("--dry-run", action="store_true", help="print instead of sending")
    run_cmd.add_argument("--no-gmail", action="store_true", help="skip Career Centre emails")
    run_cmd.add_argument("--no-workday", action="store_true", help="skip RMIT Careers")
    run_cmd.set_defaults(func=cmd_run)

    listing = sub.add_parser("list", help="show stored postings")
    listing.add_argument("--min-score", type=int, default=0)
    listing.add_argument("--limit", type=int, default=30)
    listing.set_defaults(func=cmd_list)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=args.log_level or get_settings().log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
