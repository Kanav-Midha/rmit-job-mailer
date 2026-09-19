# Architecture

A batch pipeline. Nothing runs continuously: a scheduled job fetches, stores, emails,
and exits.

```
  Career Centre saved searches ──▶ Gmail ──┐
                                            ├──▶ parse ──▶ dedupe ──▶ classify
  RMIT Careers (Workday JSON) ─────────────┘                            │
                                                                        ▼
                                                                      score
                                                                        │
                                                                        ▼
                                                                   ┌─────────┐
                                                                   │  jobs   │
                                                                   └────┬────┘
                                                                        │ never emailed
                                                                        ▼
                                                               one digest email
```

## Two kinds of source

`MessageSource` returns `RawMessage` objects that still need parsing — emails.
`PostingSource` returns `RawPosting` objects directly — structured feeds like Workday.
The runner handles both, so adding a structured source needs no parser.

## Why one digest instead of one email per job

The Career Centre alone adds 150+ postings weekly. Individual emails would be worse
than the problem being solved. One digest, grouped by category and ranked within each
group, is scannable in under a minute.

## The ordering that prevents lost postings

The runner sends the email **before** marking anything as emailed:

1. Collect and store everything new.
2. Select all jobs where `emailed_at IS NULL`.
3. Send the digest.
4. Only then set `emailed_at`.

If step 3 fails, nothing is marked, so the next run picks up the same postings plus
any newer ones. The alternative ordering loses postings silently on any SMTP hiccup —
which is the one failure this tool must not have. `test_send_failure_leaves_postings_pending_for_the_next_run`
covers exactly this.

## Idempotency

Fetching is read-only. Parsing is pure. Storage looks up a content hash before
inserting. Emailing checks `emailed_at`. A run that dies halfway can simply be run
again, which is what makes an unattended cron schedule safe.

## Failure containment

A source that fails is logged and skipped; the others still run. A message that fails
to parse is logged and skipped; the others still process. Errors accumulate in
`RunResult.errors` and are printed at the end rather than crashing the run.

## Data model

One table. `content_hash` is a SHA-256 of the normalised title, employer and location —
deliberately excluding the URL, because the same posting arrives with different
tracking parameters on different days. `emailed_at` is the send ledger.

## Scaling

Volume is tens of postings per day, which SQLite does not notice. The fuzzy duplicate
check is O(n) over one source's jobs, which is the first thing to revisit at tens of
thousands of rows. `DATABASE_URL` is the only change needed to move to Postgres.
