"""Relevance scoring, 0-100.

With NOTIFY_MIN_SCORE=0 every new posting is emailed, so the score's job is to
order the digest - the most relevant roles appear at the top of each section.
Raise NOTIFY_MIN_SCORE in .env if you want it to filter as well as rank.

Edit the rules below, not the scoring logic, when your circumstances change.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

from tracker.models import Category
from tracker.schemas import RawPosting


class Rule(NamedTuple):
    pattern: str
    weight: int
    label: str


CATEGORY_WEIGHTS: dict[Category, int] = {
    Category.SOFTWARE_ENGINEERING: 35,
    Category.MACHINE_LEARNING: 30,
    Category.DATA_SCIENCE: 28,
    Category.CYBERSECURITY: 25,
    Category.CAMPUS: 22,
    Category.OTHER: 0,
}

STAGE_SIGNALS = [
    Rule(r"\bintern(ship)?\b", 18, "internship"),
    Rule(r"\b(penultimate|second[- ]?last) year\b", 18, "penultimate year"),
    Rule(r"\bvacation (program|student)\b|\bsummer (intern|program)\b", 18, "summer program"),
    Rule(r"\bgraduate\b|\bgrad program\b", 16, "graduate role"),
    Rule(r"\bentry[- ]?level\b|\bjunior\b", 14, "entry level"),
    Rule(r"\bcadet(ship)?\b|\btrainee\b", 12, "cadetship"),
    Rule(r"\bstudent\b", 12, "open to students"),
    Rule(r"\bcasual\b|\bpart[- ]?time\b", 8, "casual or part time"),
]

SKILLS = [
    Rule(r"\bpython\b", 6, "Python"),
    Rule(r"\bjava\b(?!script)", 6, "Java"),
    Rule(r"\bc\+\+", 5, "C++"),
    Rule(r"\bsql\b", 5, "SQL"),
    Rule(r"\b(spring|spring ?boot)\b", 5, "Spring"),
    Rule(r"\b(docker|kubernetes|terraform)\b", 5, "containers or IaC"),
    Rule(r"\b(aws|azure|gcp|cloud)\b", 5, "cloud"),
    Rule(r"\b(pytorch|tensorflow|scikit|pandas|numpy)\b", 5, "ML libraries"),
    Rule(r"\b(react|node|javascript|typescript)\b", 4, "JS ecosystem"),
    Rule(r"\b(rest|api|microservice)\b", 3, "APIs"),
]
SKILL_CAP = 20

LOCATIONS = [
    Rule(r"\bmelbourne\b", 14, "Melbourne"),
    Rule(r"\bcity campus\b|\bon[- ]?campus\b", 12, "on campus"),
    Rule(r"\b(vic|victoria)\b", 10, "Victoria"),
    Rule(r"\b(remote|hybrid|work from home)\b", 8, "remote or hybrid"),
    Rule(r"\baustralia\b", 4, "Australia"),
]

PENALTIES = [
    Rule(
        r"\b(australian citizen|citizenship required|security clearance|nv1|nv2|"
        r"baseline clearance)\b",
        -35,
        "citizenship or clearance required",
    ),
    Rule(r"\bpermanent resident(s|hip)? only\b", -30, "permanent residents only"),
    Rule(r"\bsenior\b|\blead\b|\bprincipal\b|\bstaff engineer\b", -25, "senior level"),
    Rule(r"\bmanager\b|\bhead of\b|\bdirector\b", -25, "management role"),
    Rule(r"\b\d+\+? years(?:'|\u2019)? experience\b", -20, "years of experience required"),
    Rule(r"\bphd\b|\bmasters? degree required\b", -15, "postgraduate degree required"),
    Rule(r"\b(sydney|brisbane|perth|adelaide|canberra|hobart|darwin)\b", -8, "interstate"),
]


def _apply(rules: list[Rule], haystack: str, title: str, reasons: list[str]) -> int:
    total = 0
    for rule in rules:
        if re.search(rule.pattern, title) or re.search(rule.pattern, haystack):
            total += rule.weight
            reasons.append(f"{'+' if rule.weight >= 0 else ''}{rule.weight} {rule.label}")
    return total


def score(posting: RawPosting, category: Category) -> tuple[int, str]:
    haystack = " ".join(
        filter(None, [posting.title, posting.company, posting.location, posting.description])
    ).lower()
    title = (posting.title or "").lower()
    reasons: list[str] = []

    base = CATEGORY_WEIGHTS.get(category, 0)
    if base:
        reasons.append(f"+{base} {category.value.replace('_', ' ')}")
    total = base

    total += _apply(STAGE_SIGNALS, haystack, title, reasons)

    skill_reasons: list[str] = []
    skill_total = _apply(SKILLS, haystack, title, skill_reasons)
    if skill_total > SKILL_CAP:
        reasons.append(f"+{SKILL_CAP} matching skills (capped)")
        skill_total = SKILL_CAP
    else:
        reasons.extend(skill_reasons)
    total += skill_total

    total += _apply(LOCATIONS, haystack, title, reasons)
    total += _apply(PENALTIES, haystack, title, reasons)

    if posting.closes_at:
        closes = posting.closes_at
        if closes.tzinfo is None:
            closes = closes.replace(tzinfo=UTC)
        remaining = closes - datetime.now(UTC)
        if timedelta(0) < remaining <= timedelta(days=5):
            total += 8
            reasons.append("+8 closing within 5 days")
        elif remaining <= timedelta(0):
            total -= 40
            reasons.append("-40 already closed")

    return max(0, min(100, total)), "; ".join(reasons) if reasons else "no matching signals"
