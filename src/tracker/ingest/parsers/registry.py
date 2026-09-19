"""Routes a message to the right parser based on who sent it."""

from __future__ import annotations

import re
from collections.abc import Callable

from tracker.ingest.base import RawMessage
from tracker.ingest.parsers import careercentre
from tracker.schemas import RawPosting

Parser = Callable[[RawMessage], list[RawPosting]]

ROUTES: list[tuple[re.Pattern[str], Parser]] = [
    (re.compile(r"careercentre\.me", re.I), careercentre.parse),
]


def parser_for(message: RawMessage) -> Parser:
    haystack = f"{message.sender} {message.subject}"
    for pattern, parser in ROUTES:
        if pattern.search(haystack):
            return parser
    return careercentre.parse


def parse_message(message: RawMessage) -> list[RawPosting]:
    return parser_for(message)(message)
