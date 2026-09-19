"""Sends the digest over SMTP.

Gmail rejects your account password. You need an App Password, which requires
2-Step Verification to be on:
  https://myaccount.google.com/apppasswords

Put it in .env (gitignored) or a GitHub Actions secret. It is a credential with
send-mail rights on your account: never commit it, and revoke it from the same
page if it is ever exposed.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from tracker.config import get_settings
from tracker.models import Job
from tracker.notify.digest import build_html, build_text, subject_line

logger = logging.getLogger(__name__)


class MailError(RuntimeError):
    pass


class DigestMailer:
    channel = "email"

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        mail_to: str | None = None,
        mail_from: str | None = None,
    ):
        s = get_settings()
        self.host = host or s.smtp_host
        self.port = port or s.smtp_port
        self.username = username or s.smtp_username
        self.password = password or s.smtp_password
        self.mail_to = mail_to or s.mail_to
        self.mail_from = mail_from or s.mail_from or self.username

        missing = [
            name
            for name, value in [
                ("SMTP_USERNAME", self.username),
                ("SMTP_PASSWORD", self.password),
                ("MAIL_TO", self.mail_to),
            ]
            if not value
        ]
        if missing:
            raise MailError(f"Email is not configured. Set {', '.join(missing)} in .env")

    def build_message(self, jobs: list[Job]) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = subject_line(jobs)
        message["From"] = self.mail_from
        message["To"] = self.mail_to
        message.set_content(build_text(jobs))
        message.add_alternative(build_html(jobs), subtype="html")
        return message

    def send(self, jobs: list[Job]) -> None:
        if not jobs:
            logger.info("Nothing new; no email sent.")
            return

        message = self.build_message(jobs)
        context = ssl.create_default_context()
        try:
            with smtplib.SMTP(self.host, self.port, timeout=30) as server:
                server.starttls(context=context)
                server.login(self.username, self.password)
                server.send_message(message)
        except smtplib.SMTPAuthenticationError as exc:
            raise MailError(
                "SMTP rejected the login. For Gmail you need an App Password "
                "(https://myaccount.google.com/apppasswords), not your normal password, "
                "and 2-Step Verification must be on."
            ) from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise MailError(f"Could not send the digest: {exc}") from exc

        logger.info("Emailed %d postings to %s", len(jobs), self.mail_to)


class ConsolePrinter:
    """Prints the digest instead of sending it. Used by --dry-run."""

    channel = "console"

    def send(self, jobs: list[Job]) -> None:
        if not jobs:
            print("Nothing new since the last run.")
            return
        print(f"Subject: {subject_line(jobs)}")
        print()
        print(build_text(jobs))
