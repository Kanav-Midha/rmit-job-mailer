"""Reads Career Centre alert emails from Gmail, read-only.

The Career Centre sits behind a login and its terms do not permit automated access,
but it offers saved-search email alerts. Parsing mail you legitimately receive is
the clean way in. See docs/adr/0001-sources-and-terms-of-use.md.

Setup:
  1. Google Cloud Console -> new project -> enable the Gmail API.
  2. Create OAuth client credentials (Desktop app), download as credentials.json.
  3. pip install -e ".[gmail]"
  4. python -m tracker.cli auth
"""

from __future__ import annotations

import base64
import logging
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from tracker.config import get_settings
from tracker.ingest.base import MessageSource, RawMessage

logger = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class GmailAuthError(RuntimeError):
    pass


def _load_credentials(interactive: bool = False):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:  # pragma: no cover
        raise GmailAuthError(
            'Gmail support is an optional extra. Install it with: pip install -e ".[gmail]"'
        ) from exc

    settings = get_settings()
    token_path = Path(settings.gmail_token_file)
    creds_path = Path(settings.gmail_credentials_file)
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
        return creds
    if not interactive:
        raise GmailAuthError(
            f"No valid Gmail token at {token_path}. Run: python -m tracker.cli auth"
        )
    if not creds_path.exists():
        raise GmailAuthError(
            f"Missing {creds_path}. Download OAuth client credentials from Google Cloud Console."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0)
    token_path.write_text(creds.to_json())
    logger.info("Wrote Gmail token to %s", token_path)
    return creds


def authorise() -> None:
    _load_credentials(interactive=True)


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")


def _walk_parts(payload: dict) -> tuple[str, str]:
    html, text = "", ""
    stack = [payload]
    while stack:
        part = stack.pop()
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data:
            if mime == "text/html" and not html:
                html = _decode(data)
            elif mime == "text/plain" and not text:
                text = _decode(data)
        stack.extend(part.get("parts", []) or [])
    return html, text


class GmailSource(MessageSource):
    name = "gmail"

    def __init__(self, query: str | None = None, max_results: int | None = None):
        settings = get_settings()
        self.query = query or settings.gmail_query
        self.max_results = max_results or settings.gmail_max_results

    def fetch(self) -> list[RawMessage]:
        from googleapiclient.discovery import build

        service = build("gmail", "v1", credentials=_load_credentials(), cache_discovery=False)
        listing = (
            service.users()
            .messages()
            .list(userId="me", q=self.query, maxResults=self.max_results)
            .execute()
        )
        ids = [m["id"] for m in listing.get("messages", [])]
        logger.info("Gmail returned %d messages for query %r", len(ids), self.query)

        messages: list[RawMessage] = []
        for message_id in ids:
            full = (
                service.users().messages().get(userId="me", id=message_id, format="full").execute()
            )
            payload = full.get("payload", {})
            headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
            html, text = _walk_parts(payload)

            received = None
            if raw_date := headers.get("date"):
                try:
                    received = parsedate_to_datetime(raw_date)
                except (TypeError, ValueError):
                    received = None

            messages.append(
                RawMessage(
                    message_id=message_id,
                    subject=headers.get("subject", ""),
                    sender=headers.get("from", ""),
                    received_at=received or datetime.now(UTC),
                    html=html,
                    text=text,
                )
            )
        return messages
