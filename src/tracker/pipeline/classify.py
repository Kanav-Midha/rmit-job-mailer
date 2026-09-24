"""Rule-based classification. Used to group the digest into readable sections."""

from __future__ import annotations

import re

from tracker.models import Category
from tracker.schemas import RawPosting

RULES: list[tuple[Category, list[tuple[str, int]]]] = [
    (
        Category.CAMPUS,
        [
            (r"\bstudent ambassador\b", 10),
            (r"\bcampus\b", 2),
            (r"\b(peer mentor|student mentor|learning assistant|lab demonstrator)\b", 8),
            (r"\bpeer (advisor|adviser|support|tutor|leader|coach)\b", 9),
            (
                # One optional word between, for titles like
                # "Student Learning Adviser" and "Student Services Assistant".
                r"\bstudent (\w+ )?(advisor|adviser|assistant|leader|representative|"
                r"partner|supervisor)\b",
                8,
            ),
            (r"\b(note ?taker|exam supervisor|invigilator)\b", 8),
            # Library work is one of the most common casual student jobs on campus.
            # Scoped to the junior titles: "Manager, Library Services" is staff.
            (r"\blibrary (assistant|officer|attendant|aide|shelver)\b", 9),
            (r"\b(orientation|welcome) (leader|assistant|guide|crew)\b", 9),
            (r"\b(campus |student )?tour guide\b", 8),
            (r"\bstudent (life|engagement|experience|support)\b", 6),
            (r"\b(casual|student) (tutor|demonstrator|marker)\b", 8),
            (r"\b(casual|sessional)\b.*\b(student|tutor|assistant)\b", 6),
            (r"\bopen day\b", 5),
        ],
    ),
    (
        Category.MACHINE_LEARNING,
        [
            (r"\bmachine learning\b", 10),
            (r"\b(ml|ai) engineer\b", 10),
            (r"\bdeep learning\b", 8),
            (r"\b(llm|large language model|genai|generative ai)\b", 8),
            (r"\b(pytorch|tensorflow|hugging ?face)\b", 6),
            (r"\bcomputer vision\b|\bnlp\b", 6),
            (r"\bmlops\b", 8),
        ],
    ),
    (
        Category.CYBERSECURITY,
        [
            (r"\b(cyber ?security|information security|infosec)\b", 10),
            (r"\b(penetration test\w*|pen ?test\w*|red team|blue team)\b", 8),
            (r"\bsoc analyst\b|\bsecurity analyst\b", 8),
            (r"\b(vulnerability|threat intelligence|incident response)\b", 6),
            (r"\bappsec\b|\bapplication security\b", 7),
        ],
    ),
    (
        Category.DATA_SCIENCE,
        [
            (r"\bdata scien(ce|tist)\b", 10),
            (r"\bdata engineer\b", 9),
            (r"\bdata analy(st|tics)\b", 8),
            (r"\b(business intelligence|bi analyst)\b", 6),
            (r"\b(sql|power ?bi|tableau|snowflake|databricks)\b", 4),
            (r"\banalytics\b", 3),
        ],
    ),
    (
        Category.SOFTWARE_ENGINEERING,
        [
            (r"\bsoftware (engineer|developer|development)\b", 10),
            (r"\b(backend|back[- ]end|frontend|front[- ]end|full[- ]?stack)\b", 8),
            (r"\b(devops|platform engineer|site reliability|sre)\b", 8),
            (r"\bengineering intern\b", 7),
            (r"\bdeveloper\b|\bprogrammer\b", 6),
            (r"\bqa engineer\b|\btest engineer\b|\bsoftware test\b", 6),
            (r"\bcloud engineer\b|\baws\b|\bazure\b", 5),
            (r"\b(java|python|c\+\+|golang|typescript|javascript|react|spring)\b", 4),
        ],
    ),
]

MIN_SCORE = 6


def classify(posting: RawPosting) -> Category:
    haystack = " ".join(
        filter(None, [posting.title, posting.company, posting.location, posting.description])
    ).lower()
    if not haystack.strip():
        return Category.OTHER

    title = (posting.title or "").lower()
    best_category, best_score = Category.OTHER, 0

    for category, patterns in RULES:
        total = 0
        for pattern, weight in patterns:
            if re.search(pattern, title):
                total += weight * 2
            elif re.search(pattern, haystack):
                total += weight
        if total > best_score:
            best_category, best_score = category, total

    return best_category if best_score >= MIN_SCORE else Category.OTHER
