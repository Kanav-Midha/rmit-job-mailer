# RMIT Job Mailer

![CI](https://github.com/Kanav-Midha/rmit-job-mailer/actions/workflows/ci.yml/badge.svg)

Collects new job postings from RMIT's job boards twice a day and emails you one
ranked digest. No frontend, no dashboard, no app to check — it arrives in your inbox.

```
  Career Centre alerts ──▶ Gmail ──┐
                                    ├──▶ dedupe ──▶ rank ──▶ one digest email
  RMIT Careers (Workday) ──────────┘
```

## What it does

- Reads **Career Centre** saved-search alert emails from Gmail, read-only. It does not
  scrape the portal and stores no university credentials.
- Reads **RMIT Careers** (RMIT's own Workday site) for casual on-campus roles like
  student ambassador, peer mentor and library assistant. Checks `robots.txt`, rate
  limits itself, and backs off on 403 or 429.
- Deduplicates on a content hash with a fuzzy fallback, so a posting that appears in
  every daily alert for a fortnight is emailed exactly once.
- Groups by category — software engineering, machine learning, data science,
  cybersecurity, on-campus, everything else — and ranks within each group by how well
  it fits a third-year international student in Melbourne.
- Sends one email. Never the same posting twice. Never drops one on a send failure.

By default every new posting is emailed, ranked rather than filtered. Raise
`NOTIFY_MIN_SCORE` in `.env` if you want it to filter too.

## Quick start

```bash
git clone https://github.com/Kanav-Midha/rmit-job-mailer.git
cd rmit-job-mailer
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

pytest                                  # 34 tests, no network needed
python -m tracker.cli init-db
python -m tracker.cli run --dry-run --no-gmail   # prints a digest from RMIT Careers
```

`--dry-run` prints the digest instead of sending it, so you can see the output before
configuring anything.

## Setup, in order

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

Then check it works:

```bash
python -m tracker.cli check        # shows what is and is not configured
python -m tracker.cli test-email   # sends a sample digest so you can see the format
```

**2. Career Centre saved searches.** On [rmit.careercentre.me](https://rmit.careercentre.me),
run a job search and press **Save** so it emails you when new postings match. Make one
per area: software engineering, data science, machine learning, cybersecurity.

This step determines coverage. The tracker can only see what your saved searches send,
and it has no way of knowing what a too-narrow search is missing.

**3. Gmail reading.** Create a project in the Google Cloud Console, enable the Gmail
API, create OAuth client credentials of type Desktop app, download as
`credentials.json` in the project root. Then:

```bash
pip install -e ".[gmail]"
python -m tracker.cli auth      # opens a browser once, writes token.json
```

Both files are gitignored.

**4. Run it.**

```bash
python -m tracker.cli run --dry-run    # see the digest
python -m tracker.cli run              # send it
```

## Commands

| Command | What it does |
|---------|--------------|
| `tracker check` | Show what is configured, without sending |
| `tracker test-email` | Send a sample digest to check formatting |
| `tracker run` | Collect and email |
| `tracker run --dry-run` | Print the digest instead of sending |
| `tracker run --no-gmail` | Skip Career Centre emails |
| `tracker run --no-workday` | Skip RMIT Careers |
| `tracker list` | Show what is stored and what has been sent |
| `tracker auth` | One-off Gmail consent |

## Scheduling

[`.github/workflows/poll.yml`](.github/workflows/poll.yml) runs it twice daily on
GitHub Actions, free.

**SQLite will not work for scheduled runs.** Each run gets a fresh runner and the file
is discarded, so every posting would look new and you would be emailed the same jobs
forever. Use a free Postgres tier (Supabase or Neon) for `DATABASE_URL`.

Required secrets: `MAIL_TO`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `DATABASE_URL`,
`GMAIL_TOKEN_JSON`, `GMAIL_CREDENTIALS_JSON`.

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
penalised heavily because they are not open to an international student. Interstate
roles are penalised mildly. Change these to match your circumstances.

## The parser needs your real emails

[`careercentre.py`](src/tracker/ingest/parsers/careercentre.py) is written against the
general shape of these alerts and tested against synthetic fixtures. RMIT publishes no
schema and changes templates without notice.

Your first real task: save one genuine alert email, **redact your address and any
recruiter contact details**, put it in `tests/fixtures/emails/`, write a test, and tune
until it passes. Files matching `*_real.eml` are gitignored so an unredacted capture
cannot be committed by accident.

## Terms of use

Career Centre is read only through email alerts it offers deliberately — the portal is
never scraped and no university credentials are stored. RMIT Careers is read through
the public JSON endpoint its own public page uses, with `robots.txt` checked first and
conservative rate limiting.

This is not legal advice. Read RMIT's terms and satisfy yourself before running the
Workday source on a schedule. `ENABLE_WORKDAY=false` turns it off, and that site's own
"create job alert" feature is the fallback — those emails get ingested through Gmail
like any other alert. The reasoning is in
[ADR 0001](docs/adr/0001-sources-and-terms-of-use.md).

## Project layout

```
src/tracker/
  ingest/       Gmail and Workday sources, Career Centre email parser
  pipeline/     dedupe, classify, score, runner
  notify/       digest builder and SMTP sender
docs/           architecture and the sources ADR
tests/          34 tests, no network required
```

## Licence

MIT
