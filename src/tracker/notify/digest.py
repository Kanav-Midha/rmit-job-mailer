"""Builds the digest email: plain text and HTML, grouped by category.

Email clients are not browsers. No external CSS, no <style> blocks that Gmail will
strip, no web fonts, no flexbox. Inline styles on table elements only, and a plain
text part that is genuinely readable on its own.
"""

from __future__ import annotations

import html
import math
from collections import defaultdict
from datetime import UTC, datetime

from tracker.models import CATEGORY_LABELS, CATEGORY_ORDER, Job

MAX_DESC = 220


def _group(jobs: list[Job]) -> dict:
    grouped = defaultdict(list)
    for job in jobs:
        grouped[job.category].append(job)
    for bucket in grouped.values():
        bucket.sort(key=lambda j: (-j.score, j.title))
    return grouped


def _closing_note(job: Job) -> str | None:
    """Days remaining, rounded UP.

    timedelta.days truncates, so a deadline 47 hours away reports as 1 day. Under
    stating a deadline is the one error this tool must not make, so round up and
    treat anything under 24 hours as closing today.
    """
    if not job.closes_at:
        return None
    closes = job.closes_at
    if closes.tzinfo is None:
        closes = closes.replace(tzinfo=UTC)

    seconds = (closes - datetime.now(UTC)).total_seconds()
    if seconds <= 0:
        return "closed"
    if seconds < 86400:
        return "closes today"

    days = math.ceil(seconds / 86400)
    if days <= 7:
        return f"closes in {days} days"
    return f"closes {closes:%d %b}"


def subject_line(jobs: list[Job]) -> str:
    count = len(jobs)
    if count == 1:
        return f"1 new RMIT job: {jobs[0].title[:60]}"
    top = max(jobs, key=lambda j: j.score)
    return f"{count} new RMIT jobs, top match: {top.title[:50]}"


def build_text(jobs: list[Job]) -> str:
    lines = [
        f"{len(jobs)} new posting{'s' if len(jobs) != 1 else ''} since the last check.",
        "Sorted by how well each matches your profile.",
        "",
    ]
    grouped = _group(jobs)
    for category in CATEGORY_ORDER:
        bucket = grouped.get(category)
        if not bucket:
            continue
        label = CATEGORY_LABELS[category]
        lines.append(f"{label.upper()} ({len(bucket)})")
        lines.append("-" * len(f"{label} ({len(bucket)})"))
        for job in bucket:
            lines.append(f"[{job.score:3d}] {job.title}")
            meta = " | ".join(filter(None, [job.company, job.location, _closing_note(job)]))
            if meta:
                lines.append(f"      {meta}")
            if job.url:
                lines.append(f"      {job.url}")
            lines.append("")
        lines.append("")
    lines.append("Sent by your RMIT job mailer. Scores are yours to tune in score.py.")
    return "\n".join(lines)


def build_html(jobs: list[Job]) -> str:
    def esc(value: str | None) -> str:
        return html.escape(value or "")

    grouped = _group(jobs)
    parts = [
        '<body style="margin:0;padding:0;background:#f4f5f7;">',
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#f4f5f7;padding:24px 12px;">',
        '<tr><td align="center">',
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:640px;background:#ffffff;border:1px solid #d9dee5;'
        'border-radius:6px;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\','
        "Roboto,Helvetica,Arial,sans-serif;\">",
        '<tr><td style="padding:22px 24px 8px;border-bottom:2px solid #16202b;">',
        f'<div style="font-size:17px;font-weight:600;color:#16202b;">'
        f"{len(jobs)} new posting{'s' if len(jobs) != 1 else ''}</div>",
        '<div style="font-size:13px;color:#5a6773;padding-top:3px;">'
        "Ranked by fit. Highest first in each section.</div>",
        "</td></tr>",
    ]

    for category in CATEGORY_ORDER:
        bucket = grouped.get(category)
        if not bucket:
            continue
        parts.append(
            '<tr><td style="padding:18px 24px 6px;">'
            f'<div style="font-size:13px;font-weight:600;color:#16202b;">'
            f"{esc(CATEGORY_LABELS[category])} ({len(bucket)})</div></td></tr>"
        )
        for job in bucket:
            colour = "#1f4fd8" if job.score >= 60 else "#16202b" if job.score >= 40 else "#8b94a0"
            title = esc(job.title)
            heading = (
                f'<a href="{esc(job.url)}" style="color:#16202b;text-decoration:none;">{title}</a>'
                if job.url
                else title
            )
            meta_bits = [esc(job.company), esc(job.location)]
            if note := _closing_note(job):
                colour_note = "#9a6300" if "day" in note or "today" in note else "#5a6773"
                meta_bits.append(f'<span style="color:{colour_note};">{esc(note)}</span>')
            meta = " &nbsp;/&nbsp; ".join(filter(None, meta_bits))

            desc = ""
            if job.description:
                snippet = " ".join(job.description.split())[:MAX_DESC]
                if snippet:
                    desc = (
                        f'<div style="font-size:12px;color:#8b94a0;padding-top:4px;'
                        f'line-height:1.5;">{esc(snippet)}…</div>'
                    )

            parts.append(
                '<tr><td style="padding:0 24px;">'
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
                'style="border-bottom:1px solid #e6e9ee;">'
                '<tr><td width="44" valign="top" style="padding:10px 0;font-size:17px;'
                f'font-weight:600;color:{colour};">{job.score}</td>'
                '<td valign="top" style="padding:10px 0;">'
                f'<div style="font-size:14px;font-weight:600;color:#16202b;'
                f'line-height:1.4;">{heading}</div>'
                f'<div style="font-size:12px;color:#5a6773;padding-top:2px;">{meta}</div>'
                f"{desc}</td></tr></table></td></tr>"
            )

    parts.append(
        '<tr><td style="padding:18px 24px 22px;font-size:11px;color:#8b94a0;'
        'border-top:1px solid #e6e9ee;">'
        "Sent by your RMIT job mailer. Scores are yours to tune in score.py."
        "</td></tr></table></td></tr></table></body>"
    )
    return "".join(parts)
