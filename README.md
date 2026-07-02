# 18Birdies Recurring Bug Detection

Detects recurring customer-reported product issues from the CS product feedback spreadsheet and sends Slack alerts only when recurring-issue thresholds are met.

This is no longer a daily digest of every bug. The system maintains Issue Memory in a separate Google Sheet and alerts when issue volume grows or a patched issue appears to regress.

## Data Flow

GitHub Actions runs daily at 8 AM Los Angeles time:

1. Read recent source reports from monthly tabs in the product feedback spreadsheet.
2. Parse dates, feedback text, platform, device, app version, premium status, user id, tags, club/course metadata.
3. Include `Category = Bug` plus non-bug rows whose text clearly describes broken behavior.
4. Use OpenAI-assisted matching to group reports into recurring issues and match existing Issue Memory rows.
5. Update Issue Memory, Matched Reports Log, and Alert Log.
6. Send concise Slack alerts only when thresholds are met.

## Setup

```bash
cd /Users/ethanchung/Desktop/Code\ Projects/daily_slack_bugs
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env` for local dry-runs:

- `PRODUCT_FEEDBACK_SPREADSHEET_ID`
- `ISSUE_MEMORY_SPREADSHEET_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `PRODUCT_FEEDBACK_SLACK_WEBHOOK_URL`
- `SLACK_BOT_TOKEN`
- `SLACK_CHANNEL_ID`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- threshold vars, if overriding defaults

Share the source feedback spreadsheet with the service account as a viewer. Share the Issue Memory spreadsheet with the service account as an editor.

## Issue Memory Spreadsheet

Create a separate Google Sheet and use its ID as `ISSUE_MEMORY_SPREADSHEET_ID`.

The script creates or updates these tabs:

- `Issue Memory`
- `Alert Log`
- `Matched Reports Log`

Supported issue statuses:

- `Monitoring`
- `Acknowledged`
- `Open`
- `Escalated`
- `Patched`
- `Resolved`
- `Closed`
- `Dismissed`

Interactive Slack alerts store message state in these Issue Memory columns:

- `slack_channel_id`
- `slack_message_ts`
- `slack_message_url`
- `last_slack_update_sent`
- `acknowledged_at`
- `acknowledged_by`
- `resolved_at`
- `resolved_by`

Button clicks are recorded in the `Issue Actions Log` tab.

## Run Locally

Dry-run without writing Sheets or posting Slack:

```bash
.venv/bin/python run_detection.py --dry-run
```

Dry-run for a specific run date:

```bash
.venv/bin/python run_detection.py --dry-run --run-date 2026-07-01
```

Run live:

```bash
.venv/bin/python run_detection.py
```

The legacy daily digest command still exists temporarily for manual troubleshooting only. It is not used by production scheduling:

```bash
.venv/bin/python daily_bug_digest.py --dry-run
```

Do not schedule this project with local cron. GitHub Actions is the production scheduler so alerts continue to run when your laptop is off.

## GitHub Actions

Production scheduling lives in `.github/workflows/daily-bug-digest.yml`. The workflow runs daily at 8 AM Los Angeles time and can also be triggered manually.

Add repository secrets:

- `GOOGLE_SERVICE_ACCOUNT_JSON`: full JSON key contents.
- `PRODUCT_FEEDBACK_SLACK_WEBHOOK_URL`: Slack incoming webhook URL.
- `SLACK_BOT_TOKEN`: Slack bot token with `chat:write`.
- `SLACK_CHANNEL_ID`: Slack channel ID for recurring bug alerts.
- `OPENAI_API_KEY`: OpenAI API key.

Optional repository variables:

- `ISSUE_MEMORY_SPREADSHEET_ID` if replacing the default Issue Memory spreadsheet.
- `OPENAI_MODEL`
- `ROLLING_WINDOW_DAYS`
- `NEW_ISSUE_THRESHOLD`
- `HIGH_IMPACT_THRESHOLD`
- `EXISTING_UPDATE_THRESHOLD`
- `PATCHED_ALERT_THRESHOLD`
- `HIGH_IMPACT_TERMS`

Manual workflow runs default to dry-run mode. Set `dry_run=false` only when you want to post Slack alerts and write Issue Memory changes.

## Slack Interactivity

Incoming webhooks cannot update prior messages, so interactive alerts use the Slack Web API when `SLACK_BOT_TOKEN` and `SLACK_CHANNEL_ID` are configured.

To enable buttons:

1. Create or update a Slack app with bot scope `chat:write`.
2. Invite the bot to the dedicated alert channel.
3. Deploy `slack_interactions_apps_script.js` as a Google Apps Script web app.
4. Set Apps Script properties:
   - `ISSUE_MEMORY_SPREADSHEET_ID`
   - `SLACK_BOT_TOKEN`
   - `SLACK_INTERACTION_SECRET`
   - optional `SLACK_ALLOWED_TEAM_ID`
   - optional `SLACK_ALLOWED_API_APP_ID`
5. In Slack app settings, enable Interactivity and set the Request URL to:

```text
https://script.google.com/macros/s/YOUR_DEPLOYMENT_ID/exec?secret=YOUR_SLACK_INTERACTION_SECRET
```

## Tests

```bash
python3 -m unittest discover -s tests
```
