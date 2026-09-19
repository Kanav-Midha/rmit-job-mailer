from __future__ import annotations

import email
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tracker import db as db_module
from tracker.config import get_settings
from tracker.ingest.base import RawMessage

FIXTURES = Path(__file__).parent / "fixtures" / "emails"


def load_eml(name: str) -> RawMessage:
    raw = (FIXTURES / name).read_text(encoding="utf-8")
    parsed = email.message_from_string(raw)
    body = parsed.get_payload()
    is_html = "html" in (parsed.get_content_type() or "")
    return RawMessage(
        message_id=name,
        subject=parsed.get("Subject", ""),
        sender=parsed.get("From", ""),
        received_at=datetime(2026, 9, 15, tzinfo=UTC),
        html=body if is_html else "",
        text="" if is_html else body,
    )


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path/'test.db'}")
    get_settings.cache_clear()
    db_module.reset_state()
    db_module.init_db()
    with db_module.session_scope() as s:
        yield s
    db_module.reset_state()
    get_settings.cache_clear()


@pytest.fixture
def swe_message() -> RawMessage:
    return load_eml("careercentre_swe.eml")


@pytest.fixture
def empty_message() -> RawMessage:
    return load_eml("careercentre_empty.eml")
