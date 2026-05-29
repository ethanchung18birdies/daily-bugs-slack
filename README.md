# Daily CS Product Bug Slack Digest

Posts one daily Slack message with all CS product feedback rows marked `Bug` from the previous calendar date.

If the job runs at `8:00 AM PT` on May 29, it reports all rows from May 28.

## Setup

```bash
cd /Users/ethanchung/Desktop/Code\ Projects/daily_slack_bugs
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
mkdir -p logs
```

Fill in `.env`:

- `PRODUCT_FEEDBACK_SPREADSHEET_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `PRODUCT_FEEDBACK_SLACK_WEBHOOK_URL`
- `LOG_LEVEL`

Share the Google Sheet with the service account email as a viewer.

## Run

Dry-run against the live Google Sheet:

```bash
.venv/bin/python daily_bug_digest.py --dry-run
```

Dry-run for a specific run date:

```bash
.venv/bin/python daily_bug_digest.py --dry-run --run-date 2026-05-29
```

Dry-run against a CSV export:

```bash
.venv/bin/python daily_bug_digest.py --dry-run --run-date 2026-05-29 --csv "/Users/ethanchung/Downloads/CS Product Feedback 2026 - May.csv"
```

Post to Slack:

```bash
.venv/bin/python daily_bug_digest.py
```

## Cron

```cron
TZ=America/Los_Angeles
0 8 * * * cd /Users/ethanchung/Desktop/Code\ Projects/daily_slack_bugs && .venv/bin/python daily_bug_digest.py >> logs/daily_bug_digest.log 2>&1
```

## GitHub Actions

Use GitHub Actions if the digest should run even when this laptop is off.

1. Create a private GitHub repo for this folder.
2. Commit and push this project, excluding `.env`, `.venv/`, logs, and JSON keys.
3. In the GitHub repo, go to `Settings` > `Secrets and variables` > `Actions`.
4. Add repository secrets:
   - `GOOGLE_SERVICE_ACCOUNT_JSON`: the full contents of the service account JSON key file.
   - `PRODUCT_FEEDBACK_SLACK_WEBHOOK_URL`: the Slack incoming webhook URL.
5. The workflow in `.github/workflows/daily-bug-digest.yml` runs at 8 AM Los Angeles time every day.

GitHub cron schedules are UTC-only, so the workflow schedules both daylight-saving and standard-time UTC hours, then skips whichever run is not currently 8 AM in `America/Los_Angeles`.

You can also run it manually from the repo's `Actions` tab using `Run workflow`. For manual tests, set `dry_run=true` to print the digest without posting to Slack.

## Tests

```bash
python3 -m unittest discover -s tests
```
