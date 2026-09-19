"""Database models.

One Job row per distinct posting ever seen. `content_hash` is what makes re-running
safe: the same posting appearing in tomorrow's digest updates `last_seen_at` rather
than creating a duplicate, and `emailed_at` guarantees it is never sent twice.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Category(str, enum.Enum):
    SOFTWARE_ENGINEERING = "software_engineering"
    DATA_SCIENCE = "data_science"
    MACHINE_LEARNING = "machine_learning"
    CYBERSECURITY = "cybersecurity"
    CAMPUS = "campus"
    OTHER = "other"


CATEGORY_LABELS: dict[Category, str] = {
    Category.SOFTWARE_ENGINEERING: "Software engineering",
    Category.DATA_SCIENCE: "Data science",
    Category.MACHINE_LEARNING: "Machine learning",
    Category.CYBERSECURITY: "Cybersecurity",
    Category.CAMPUS: "On campus at RMIT",
    Category.OTHER: "Everything else",
}

# Order sections appear in the digest.
CATEGORY_ORDER: list[Category] = [
    Category.SOFTWARE_ENGINEERING,
    Category.MACHINE_LEARNING,
    Category.DATA_SCIENCE,
    Category.CYBERSECURITY,
    Category.CAMPUS,
    Category.OTHER,
]


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("content_hash", name="uq_jobs_content_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)

    title: Mapped[str] = mapped_column(String(300))
    company: Mapped[str | None] = mapped_column(String(200), default=None)
    location: Mapped[str | None] = mapped_column(String(200), default=None)
    url: Mapped[str | None] = mapped_column(Text, default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)

    source: Mapped[str] = mapped_column(String(60), index=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    category: Mapped[Category] = mapped_column(Enum(Category), default=Category.OTHER, index=True)
    score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    score_reasons: Mapped[str | None] = mapped_column(Text, default=None)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Set once the posting has been included in a digest. Never emailed twice.
    emailed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Job {self.id} {self.title!r} score={self.score}>"
