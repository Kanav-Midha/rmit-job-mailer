# ADR 0002: Read company job boards directly, not aggregators

- Status: accepted, but the source is currently switched off
- Date: 2026-09

> **Update, later in 2026-09.** The Greenhouse source is built, tested and working,
> and `ENABLE_GREENHOUSE=false` in both `.env` and the scheduled workflow. The
> decision below is unchanged and the reasoning still holds: if you want graduate
> roles at technology companies, reading their boards directly is the right way to
> get them. What changed is the goal. This tracker is now scoped to RMIT's own
> vacancies, and a company board search is a different search. Setting
> `GREENHOUSE_BOARDS` and flipping the flag brings it back with no code change,
> which was the point of making it configuration.
>
> The Gmail source is off for a different reason, recorded in the Context below: it
> was never able to deliver postings in the first place.

## Context

After the first live runs, the digest was almost entirely RMIT's own staff
vacancies. Three things became clear:

1. **RMIT Careers only advertises RMIT roles.** Useful for the casual on-campus
   work it does carry, but it will never contain a graduate software role at a
   technology company.
2. **The Career Centre path does not deliver postings.** What arrives in the
   inbox is a Canvas announcement from `notifications@instructure.com` saying a
   role was added, linking to a Smartsheet report. There are no job details in
   the email. Coverage also depends on a saved search limited to three keywords.
3. **The Smartsheet behind those announcements has no machine-readable form.**
   The grid is drawn on an HTML canvas and its data arrives over an undocumented
   internal POST endpoint. Reading it would mean reverse-engineering a private
   API, which sits below HTML scraping in the ranking set out in ADR 0001.

So the sources we had could not, even working perfectly, produce the postings
this tracker exists to find.

## Decision

**Read company job boards directly through their applicant tracking systems'
public APIs, starting with Greenhouse.**

    GET https://boards-api.greenhouse.io/v1/boards/<token>/jobs

It is documented, unauthenticated, returns JSON, and its fields map onto
`RawPosting` without interpretation: `title`, `location.name`, `absolute_url`,
`first_published`, `application_deadline`. Under ADR 0001's ranking this is an
official API, which places it above the Workday endpoint already in use.

Boards are configured as a list of tokens in `GREENHOUSE_BOARDS`, so adding an
employer is a config change rather than a code change. A token that does not
exist returns 404, which the source logs and skips: a company that has moved off
Greenhouse must not break a run.

## Consequences

Good: real graduate and internship postings at real employers, from an interface
meant to be consumed programmatically. No credentials, no scraping, no parsing
heuristics that rot when someone edits an email template. The existing
classifier, scorer and dedupe needed no changes at all, which is some evidence
the pipeline boundary was drawn in the right place.

Bad: coverage is only as good as the token list, and tokens must be found by hand
from each company's careers page. Employers on Lever, Workable, SmartRecruiters
or their own systems are invisible until a source is written for each. The list
endpoint omits the job description, so classification works from title, company
and location alone; fetching each description would mean one request per posting.

Neutral: this makes the tracker less about RMIT specifically and more about a
Melbourne student job search generally. The name stays; the scope has widened.

## Next

Lever publishes a comparable public API (`api.lever.co/v0/postings/<token>`) and
is the obvious second source. The `PostingSource` interface should absorb it with
no changes elsewhere, which is the test of whether that interface was worth
having.
