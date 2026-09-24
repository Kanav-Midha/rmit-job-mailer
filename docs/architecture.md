# Architecture

A batch pipeline. Nothing runs continuously: a scheduled job fetches, stores, emails,
and exits.

```
  RMIT Careers (Workday JSON) ──▶ dedupe ──▶ classify ──▶ score
                                                           │
                                                           ▼
                                                      ┌─────────┐
                                                      │  jobs   │
                                                      └────┬────┘
                                                           │ never emailed
                                                           ▼
                                                  one digest email
```

RMIT Careers is the only source running. A Gmail source and a Greenhouse source exist
and are switched off through `ENABLE_` settings, which is why the two source shapes
below both still matter.

## Two kinds of source

`MessageSource` returns `RawMessage` objects that still need parsing, such as emails.
`PostingSource` returns `RawPosting` objects directly, from structured feeds like
Workday. The runner handles both, so adding a structured source needs no parser.

## Why one digest instead of one email per job

The first run against an empty database has a dozen or more postings to report, and
one busy week at RMIT can add several in a day. Individual emails would be worse than
the problem being solved. One digest, grouped by category and ranked within each
group, is scannable in under a minute.

## The ordering that prevents lost postings

The runner sends the email **before** marking anything as emailed:

1. Collect and store everything new.
2. Select all jobs where `emailed_at IS NULL`.
3. Send the digest.
4. Only then set `emailed_at`.

If step 3 fails, nothing is marked, so the next run picks up the same postings plus
any newer ones. The alternative ordering loses postings silently on any SMTP hiccup,
which is the one failure this tool must not have.
`test_send_failure_leaves_postings_pending_for_the_next_run` covers exactly this.

## Pagination, and how postings went missing

Workday pages 20 at a time. The obvious stopping condition, `offset + PAGE_SIZE >=
total`, is wrong: `total` is reported relative to the current offset on later pages,
so page two claimed a total of 31 against an offset of 40 and ended the loop. A live
run collected 40 of RMIT's 51 postings and said nothing about the other 11.

The loop now stops on a short page instead. Two things that used to be silent are
logged: hitting `WORKDAY_MAX_PAGES`, and collecting fewer postings than the site
reports. `test_workday.py` pins the 51 case.

## Idempotency

Fetching is read-only. Parsing is pure. Storage looks up a content hash before
inserting. Emailing checks `emailed_at`. A run that dies halfway can simply be run
again, which is what makes an unattended schedule safe.

## Failure containment, and its limit

A source that fails is logged and skipped; the others still run. A message that fails
to parse is logged and skipped; the others still process. Errors accumulate in
`RunResult.errors` and are printed at the end rather than crashing mid-run.

The run then exits non-zero if `RunResult.errors` is non-empty, which is what turns a
broken scheduled run red. Containment is about not losing the work the other sources
did, not about pretending the run succeeded.

A source that returns nothing at all is treated as broken rather than quiet. RMIT
always has Australian roles live, so `WorkdaySource` raises `SourceUnavailable` below
`WORKDAY_MIN_EXPECTED`. Without it, robots.txt being unreachable, a 403, a 429 or
changed JSON would each end in an empty list, a green run and an empty inbox, which
from the outside looks exactly like a day with no new postings.

## Data model

One table. `content_hash` is a SHA-256 of the normalised title, employer and location,
deliberately excluding the URL, because the same posting arrives with different
tracking parameters on different days. `emailed_at` is the send ledger.

## Scaling

Volume is tens of postings per day, which SQLite does not notice. The fuzzy duplicate
check is O(n) over one source's jobs, which is the first thing to revisit at tens of
thousands of rows. `DATABASE_URL` is the only change needed to move to Postgres, and
the scheduled run already uses it, because a GitHub runner is destroyed along with any
SQLite file on it.
