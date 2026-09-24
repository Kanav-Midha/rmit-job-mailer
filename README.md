# RMIT Job Mailer

![CI](https://github.com/Kanav-Midha/rmit-job-mailer/actions/workflows/ci.yml/badge.svg)

Checks RMIT's careers site every morning and emails you a ranked digest of anything
new. No frontend, no dashboard, no app to open. It arrives in your inbox, and only
when there is something in it.

```
  RMIT Careers (Workday JSON) ──▶ dedupe ──▶ classify ──▶ rank ──▶ one digest email
```

## What it does

- Reads **RMIT Careers**, RMIT's own Workday site, through the public JSON endpoint
  its own public page uses. Checks `robots.txt` first, rate limits itself, and backs
  off on 403 or 429 rather than retrying harder.
- Asks the API for **Australian campuses only**. RMIT advertises Melbourne and its
  Vietnam campuses in one feed, and the Vietnam roles outnumber the Australian ones
  roughly three to one. Filtering server side is exact; guessing from city names would
  break the first time RMIT opened a campus this code had not heard of.
- Deduplicates on a content hash with a fuzzy fallback, so a posting that stays live
  for a fortnight is emailed exactly once, on the day it appears.
- Groups by category (on campus, software engineering, machine learning, data science,
  cybersecurity, everything else) and ranks within each group by how well it fits a
  third-year international student in Melbourne.
- Sends one email. Never the same posting twice. Never drops one on a send failure.
- **Fails loudly when it collects nothing.** RMIT always has a dozen or so Australian
  roles live, so zero postings means something is broken rather than the day being
  quiet. Without this the run would exit green and send nothing, which from the inbox
  is indistinguishable from good news.

Every new posting is emailed. The score ranks the digest rather than filtering it, on
the principle that with roughly fourteen live roles a filter can only lose one. Raise
`NOTIFY_MIN_SCORE` in `.env` if you would rather it filtered too.

## Quick start

```bash
git clone https://github.com/Kanav-Midha/rmit-job-mailer.git
cd rmit-job-mailer
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

pytest                                # 78 tests, no network needed
python -m tracker.cli run --dry-run   # prints a digest, sends nothing
```

`--dry-run` prints the digest instead of sending it, so you can see the output before
configuring an inbox.

## Setup

**1. Email sending.** Gmail rejects your account password, so you need an App Password,
which requires 2-Step Verification:

- Turn on 2-Step Verification: https://myaccount.google.com/security
- Create an app password: https://myaccount.google.com/apppasswords
- Put it in `.env` with the spaces removed

```
MAIL_TO=your.address@gmail.com
MAIL_FROM=your.address@gmail.com
SMTP_USERNAME=your.address@gmail.com
SMTP_PASSWORD=abcdefghijklmnop
```

`.env` is gitignored. Never commit it. Revoke the password from the same page if it
ever leaks.

**2. Check and send.**

```bash
python -m tracker.cli check        # shows what is and is not configured
python -m tracker.cli test-email   # sends a sample digest so you can see the format
python -m tracker.cli run          # collect and email for real
```

## Commands

| Command | What it does |
|---------|--------------|
| `tracker check` | Show what is configured, without sending |
| `tracker test-email` | Send a sample digest to check formatting |
| `tracker run` | Collect and email |
| `tracker run --dry-run` | Print the digest instead of sending |
| `tracker run --no-workday` | Skip RMIT Careers |
| `tracker list` | Show what is stored and what has been sent |
| `tracker init-db` | Create the tables |

`tracker run` exits non-zero if any source failed, so a scheduled run turns red
instead of quietly sending nothing.

## Scheduling

[`.github/workflows/poll.yml`](.github/workflows/poll.yml) runs it once a day on
GitHub Actions, free.

The cron is `0 22 * * *`, which is 08:00 in Melbourne during AEST and 09:00 during
AEDT. GitHub's scheduler is UTC and does not know about daylight saving, so that hour
of drift is expected. GitHub also delays scheduled runs under load and switches the
schedule off entirely after 60 days with no commits.

**SQLite will not work for scheduled runs.** Each run gets a fresh machine and the
file is destroyed with it, so every posting would look new and the same jobs would
arrive every morning forever. Use a free Postgres tier (Neon or Supabase) for
`DATABASE_URL`, pasted exactly as the provider gives it.

Required secrets: `MAIL_TO`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `DATABASE_URL`.

Everything the scheduled run depends on is stated explicitly in the workflow's `env`
block, because `.env` is gitignored and never reaches the runner. Anything left
unstated silently falls back to the defaults in `config.py`, and the scheduled run
then behaves differently from the run you tested locally.

Turn on failure notifications so a red run reaches you: GitHub, your avatar,
Settings, Notifications, Actions.

## Tuning what gets ranked highly

Scoring lives in [`src/tracker/pipeline/score.py`](src/tracker/pipeline/score.py) as
labelled rules. Edit these, not the logic:

```python
STAGE_SIGNALS = [Rule(r"\binternship\b", 18, "internship"), ...]
SKILLS        = [Rule(r"\bpython\b", 6, "Python"), ...]
PENALTIES     = [Rule(r"\bsenior\b", -25, "senior level"), ...]
```

The defaults encode a specific situation: Melbourne, penultimate year, student visa, a
Python/Java/C++/SQL stack. Roles requiring citizenship or a security clearance are
penalised heavily because they are not open to an international student. Academic
staff roles and interstate roles are penalised too. Change these to match your own
circumstances.

`CATEGORY_WEIGHTS` in the same file decides which kind of role sorts to the top.
Which categories get emailed at all is `NOTIFY_CATEGORIES`, empty for all of them.

## Other sources, currently off

Two more sources exist in the codebase and are switched off in `.env` and in the
workflow. They are configuration, not code changes, so either can come back with one
line.

- **Career Centre** (`ENABLE_GMAIL`) reads saved-search alert emails from Gmail,
  read-only. It never scrapes the portal and stores no university credentials. It is
  off because what actually arrives is a Canvas announcement linking to a list rather
  than the list itself, so the source costs an OAuth setup and returns no postings.
  Turning it on needs `credentials.json`, `tracker auth`, and a parser tuned against
  real alert emails. See [ADR 0002](docs/adr/0002-company-boards-over-aggregators.md).
- **Company boards** (`ENABLE_GREENHOUSE`) reads any company's public Greenhouse board
  from `boards-api.greenhouse.io`. It is off because this tracker's job is RMIT's own
  vacancies; graduate roles at technology companies are a separate search. Set
  `GREENHOUSE_BOARDS` to a comma-separated list of board tokens to use it.

## Terms of use

RMIT Careers is read through the public JSON endpoint that its own public page calls,
with `robots.txt` checked before every run, a two second delay between requests, a
User-Agent that says what the tool is and who runs it, and no retry on 403 or 429. If
`robots.txt` is unreachable the source refuses to proceed rather than guessing.

This is not legal advice. Read RMIT's terms and satisfy yourself before running this
on a schedule. `ENABLE_WORKDAY=false` turns it off, and that site's own "create job
alert" feature is the fallback. The reasoning behind which sources are acceptable and
which are not is in [ADR 0001](docs/adr/0001-sources-and-terms-of-use.md).

## Project layout

```
src/tracker/
  ingest/       Workday source, plus the Gmail and Greenhouse sources currently off
  pipeline/     dedupe, classify, score, runner
  notify/       digest builder and SMTP sender
docs/           architecture and two decision records
tests/          78 tests, no network required
```

## Licence

MIT
