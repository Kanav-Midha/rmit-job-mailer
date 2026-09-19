# ADR 0001: How each source is read

- Status: accepted
- Date: 2026-09

## Context

"Every job posted on the RMIT website" is three different systems:

1. **Career Centre** (`rmit.careercentre.me`) — RMIT's student jobs board, roughly
   150+ postings added weekly. Behind a student login.
2. **RMIT Careers** (`rmit.wd3.myworkdayjobs.com`) — RMIT's own vacancies, including
   the casual on-campus work students want. Public, no login.
3. **Prosple** (`rmit.prosple.com`) — a partner graduate directory that mirrors much
   of the Career Centre.

Each needs a different access decision.

## Decision

**Career Centre: email alerts only, never scraping.** It requires a login, so scraping
would mean storing university credentials in the tracker. Automated access of an
aggregator platform is typically prohibited by its terms. The portal already offers
saved-search email alerts, which is an access path it deliberately provides. We read
those emails with read-only Gmail OAuth against the user's own mailbox.

**RMIT Careers: the site's own public JSON endpoint, politely.** Workday career sites
are single-page apps whose listings come from a public, unauthenticated JSON endpoint
on the same host. Calling it directly is lighter than rendering and scraping HTML, and
returns the same data the public page shows. Because it is still automated access, the
source reads `robots.txt` first and refuses if the path is disallowed, waits at least
one second between requests (two by default), caps pagination, sends a User-Agent that
identifies itself, and gives up on 403 or 429 rather than retrying harder.

**Prosple: not implemented.** It duplicates the Career Centre, and a third-party
commercial site deserves its own terms review before automated access.

## Consequences

Good: no third-party credentials are stored anywhere. The Career Centre path uses a
supported feature rather than working around one. Emails are trivially capturable as
test fixtures, which makes the fragile parsing logic testable offline. The Workday
path needs no auth and breaks loudly rather than silently.

Bad: Career Centre coverage is limited to what your saved searches match, so search
configuration becomes a setup step rather than a code concern — if a search is too
narrow, the tracker cannot know what it is missing. Email alerts also carry fewer
fields than the full listing. The Workday endpoint is undocumented and may change or
be restricted at any time; `ENABLE_WORKDAY=false` turns it off, and the site's own
"create job alert" feature is the fallback, ingested through Gmail like any other alert.

**This is not legal advice.** Read RMIT's terms of use and satisfy yourself before
running the Workday source on a schedule.

## Rule for future sources

Prefer, in order: a published feed, official email alerts, an official API, then the
site's own public endpoint with rate limiting. HTML scraping is the last resort and
requires checking `robots.txt` and terms first.
