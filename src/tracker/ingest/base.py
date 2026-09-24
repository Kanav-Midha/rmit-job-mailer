"""Source interface.

A Source produces either RawMessages (things that still need parsing, like emails)
or RawPostings directly (structured sources like Workday's public job feed).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from tracker.schemas import RawPosting


class SourceUnavailable(RuntimeError):
    """A source could not deliver what it should have.

    This exists to make a specific failure loud. A source that returns nothing
    looks, from the inbox, exactly like a quiet day with no new postings: the run
    exits green, no digest is sent, and nothing is wrong as far as anyone can
    tell. Raising instead turns that silence into a failed run.
    """


@dataclass
class RawMessage:
    message_id: str
    subject: str = ""
    sender: str = ""
    received_at: datetime | None = None
    html: str = ""
    text: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def body(self) -> str:
        return self.html or self.text


class MessageSource(ABC):
    """Returns raw messages that a parser must interpret."""

    name: str = "message_source"

    @abstractmethod
    def fetch(self) -> list[RawMessage]:
        raise NotImplementedError


class PostingSource(ABC):
    """Returns structured postings directly, with no parsing step."""

    name: str = "posting_source"

    @abstractmethod
    def fetch(self) -> list[RawPosting]:
        raise NotImplementedError
