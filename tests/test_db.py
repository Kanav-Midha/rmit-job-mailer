"""Database URL handling.

The scheduled run stores its state in a hosted Postgres, and its URL arrives as a
string the provider generated. Editing that string by hand before pasting it into
a GitHub secret is exactly the step that gets forgotten once and then fails at
08:00 with nobody watching, so the code accepts it as given.
"""

from __future__ import annotations

from sqlalchemy.engine import make_url

from tracker.db import POSTGRES_DRIVER, normalise_url

NEON = "postgresql://kanav:pw@ep-cool-forest-123.ap-southeast-2.aws.neon.tech/neondb?sslmode=require"


def test_a_bare_postgresql_url_is_pointed_at_the_installed_driver():
    """The [postgres] extra installs psycopg 3, but SQLAlchemy reads
    `postgresql://` as psycopg2 and raises ModuleNotFoundError on first use."""
    url = normalise_url(NEON)
    assert url.startswith(f"{POSTGRES_DRIVER}://")


def test_nothing_but_the_scheme_changes():
    """Credentials, host, database and query string must survive intact: losing
    `sslmode=require` would be rejected by Neon, and losing the password silently
    falls back to a local socket."""
    assert normalise_url(NEON).endswith(
        "kanav:pw@ep-cool-forest-123.ap-southeast-2.aws.neon.tech/neondb?sslmode=require"
    )


def test_the_legacy_postgres_scheme_is_accepted():
    """SQLAlchemy 2 refuses `postgres://` outright. Some providers still emit it."""
    assert normalise_url("postgres://u:p@host/db") == f"{POSTGRES_DRIVER}://u:p@host/db"


def test_a_url_that_names_its_driver_is_left_alone():
    """Pinning psycopg2 or asyncpg later must not be silently undone."""
    for url in (
        "postgresql+psycopg2://u:p@host/db",
        "postgresql+asyncpg://u:p@host/db",
        f"{POSTGRES_DRIVER}://u:p@host/db",
    ):
        assert normalise_url(url) == url


def test_sqlite_is_untouched():
    """Local runs and the whole test suite depend on this."""
    assert normalise_url("sqlite:///tracker.db") == "sqlite:///tracker.db"
    assert normalise_url("sqlite:///:memory:") == "sqlite:///:memory:"


def test_sqlalchemy_itself_agrees_on_the_driver():
    """Asserting on our own string proves little. This asks SQLAlchemy's parser,
    which is what actually decides which module gets imported."""
    assert make_url(normalise_url(NEON)).drivername == POSTGRES_DRIVER
    assert make_url(normalise_url("sqlite:///tracker.db")).drivername == "sqlite"


def test_the_password_never_reaches_the_log(caplog):
    """Workflow logs live for 90 days and are visible to anyone who can read the
    repository once it is public."""
    caplog.set_level("DEBUG")
    normalise_url("postgresql://user:sup3rs3cret@host/db")
    assert "sup3rs3cret" not in caplog.text
