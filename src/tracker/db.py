"""Engine and session handling."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from tracker.config import get_settings
from tracker.models import Base

logger = logging.getLogger(__name__)

_engine = None
_SessionFactory = None

# `pip install -e ".[postgres]"` brings psycopg 3, but SQLAlchemy still resolves a
# bare `postgresql://` URL to psycopg2, which this project does not install. So a
# hosted database URL that is perfectly valid fails with ModuleNotFoundError at
# the first query. Naming the driver is the whole fix.
POSTGRES_DRIVER = "postgresql+psycopg"

_LEGACY_SCHEMES = ("postgres://", "postgresql://")


def normalise_url(url: str) -> str:
    """Point a hosted-Postgres URL at the driver that is actually installed.

    A connection string has to work exactly as the provider hands it over.
    Neon, Supabase and Render all emit one of two schemes that SQLAlchemy either
    refuses or resolves to the wrong driver:

        postgres://...      SQLAlchemy 2 will not load a dialect called `postgres`
        postgresql://...    resolves to psycopg2, which is not installed

    Both become `postgresql+psycopg://`. A URL that already names its driver is
    returned untouched, so pinning psycopg2 or asyncpg later still works, and so
    does every SQLite URL.
    """
    for scheme in _LEGACY_SCHEMES:
        if url.startswith(scheme):
            # Never log the URL itself: it carries the database password, and
            # GitHub keeps workflow logs for 90 days.
            logger.debug("Rewrote the database URL scheme to %s", POSTGRES_DRIVER)
            return POSTGRES_DRIVER + "://" + url[len(scheme) :]
    return url


def get_engine():
    global _engine
    if _engine is None:
        url = normalise_url(get_settings().database_url)
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(
            url,
            echo=False,
            future=True,
            connect_args=connect_args,
            # Neon and Supabase suspend an idle database and drop its connections.
            # Without this, the first query of a scheduled run can hit a socket
            # that closed hours ago and fail the whole run.
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _SessionFactory


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    Base.metadata.create_all(get_engine())


def reset_state() -> None:
    """Drop cached engine and session factory. Used by tests that swap DATABASE_URL."""
    global _engine, _SessionFactory
    _engine = None
    _SessionFactory = None
