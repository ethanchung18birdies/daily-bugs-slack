# 18Birdies Recurring Bug Detection

Detects recurring customer-reported product issues from the CS product feedback spreadsheet and sends Slack alerts only when recurring-issue thresholds are met.

This is no longer a daily digest of every bug. The system maintains Issue Memory in a separate Google Sheet and alerts when issue volume grows or a patched issue appears to regress.

## Data Flow

cron-job.org triggers the GitHub Actions workflow daily at 8 PM Los Angeles time:

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
- `slack_message_deleted_at`
- `slack_message_deleted_by`

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

Do not schedule this project with local cron. cron-job.org is the production scheduler so alerts continue to run when your laptop is off.

## GitHub Actions

`.github/workflows/daily-bug-digest.yml` is configured for `workflow_dispatch` only. GitHub Actions runs the job, but does not schedule it. Production scheduling should call the GitHub workflow dispatch API from cron-job.org at 8 PM Los Angeles time.

Add repository secrets:

- `GOOGLE_SERVICE_ACCOUNT_JSON`: full JSON key contents.
- `PRODUCT_FEEDBACK_SLACK_WEBHOOK_URL`: Slack incoming webhook URL.
- `SLACK_BOT_TOKEN`: Slack bot token with `chat:write` and `reactions:read`.
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

Manual/API workflow runs default to dry-run mode unless the caller sends `dry_run=false`. Set `dry_run=false` only when you want to post Slack alerts and write Issue Memory changes.

## cron-job.org

Create a cron-job.org job that calls the GitHub workflow dispatch API:

```text
POST https://api.github.com/repos/ethanchung18birdies/daily-bugs-slack/actions/workflows/daily-bug-digest.yml/dispatches
```

Headers:

```text
Accept: application/vnd.github+json
Authorization: Bearer YOUR_GITHUB_TOKEN
X-GitHub-Api-Version: 2026-03-10
Content-Type: application/json
```

Body:

```json
{
  "ref": "main",
  "inputs": {
    "run_date": "",
    "dry_run": "false"
  }
}
```

## Slack Reactions

Incoming webhooks cannot update prior messages or read reactions, so interactive alerts use the Slack Web API when `SLACK_BOT_TOKEN` and `SLACK_CHANNEL_ID` are configured.

To enable lightweight status updates:

1. Create or update a Slack app with bot scopes `chat:write` and `reactions:read`.
2. Invite the bot to the dedicated alert channel.
3. Add `SLACK_BOT_TOKEN` and `SLACK_CHANNEL_ID` to GitHub repository secrets.

When an alert appears in Slack:

- React with `:eyes:` to mark the issue `Acknowledged`.
- React with `:white_check_mark:` to mark the issue `Resolved`.
- React with `:wastebasket:` to delete the Slack alert message without marking the issue resolved.

The next scheduled or manual GitHub Actions run reads reactions from each tracked Slack alert message, updates Issue Memory, and edits or deletes the same Slack parent message. `Resolved` issues continue to be matched and logged, but they stop producing Slack updates.

Existing Issue Memory rows from older workflow versions may have `last_slack_alert_sent` without `slack_message_ts`. Those rows are treated as already alerted and are suppressed rather than posted again, because the workflow cannot safely update an unknown Slack parent message.

## Tests

```bash
python3 -m unittest discover -s tests
```
