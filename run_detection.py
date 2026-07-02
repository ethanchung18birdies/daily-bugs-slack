from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
import sys
import uuid

from alert_policy import decide_alert
from config import PT, load_settings
from issue_matching import match_issues
from issue_memory import build_updated_issue, find_existing_issue, mark_alert_sent
from report_parser import month_tabs_for_window, parse_source_rows, previous_report_date, rolling_window
from sheets_client import SheetsClient
from slack_alerts import format_issue_alert, send_slack_message


LOGGER = logging.getLogger("run_detection")


def configure_logging(level_name: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level_name.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect recurring 18Birdies support bugs and alert Slack.")
    parser.add_argument("--dotenv", help="Path to .env. Defaults to .env in current directory.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned changes without writing Sheets or Slack.")
    parser.add_argument("--run-date", help="Pretend the job is running on this PT date, YYYY-MM-DD.")
    args = parser.parse_args(argv)

    settings = load_settings(args.dotenv or ".env", require_slack=not args.dry_run)
    configure_logging(settings.log_level)

    now = _parse_run_date(args.run_date) if args.run_date else datetime.now(PT)
    report_end = previous_report_date(now)
    report_start, report_end = rolling_window(report_end, settings.rolling_window_days)
    run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    sheets = SheetsClient(settings)
    if not args.dry_run:
        sheets.ensure_memory_schema()

    reports = []
    for tab_name in month_tabs_for_window(report_start, report_end):
        values = sheets.source_values(tab_name)
        reports.extend(parse_source_rows(tab_name, values, report_start, report_end))

    issues = sheets.read_issues()
    clusters = match_issues(reports, issues, settings)

    planned = []
    for cluster in clusters:
        cluster_reports = [reports[index] for index in cluster.report_indices]
        if not cluster_reports:
            continue
        existing = find_existing_issue(cluster, issues)
        updated_issue = build_updated_issue(cluster, cluster_reports, existing, now_iso)
        decision = decide_alert(
            issue=updated_issue,
            reports=cluster_reports,
            existing_issue=existing,
            settings=settings,
        )
        if decision.should_alert and not args.dry_run:
            message = format_issue_alert(decision)
            slack_ts = send_slack_message(settings.slack_webhook_url, message)
            updated_issue = mark_alert_sent(updated_issue, now_iso)
            sheets.upsert_issue(updated_issue)
            sheets.append_alert_log(
                [
                    f"alert-{uuid.uuid4().hex[:12]}",
                    updated_issue.issue_id,
                    decision.alert_type,
                    now_iso,
                    decision.rolling_window_count,
                    decision.new_since_last_alert,
                    "",
                    slack_ts,
                    decision.reason,
                ]
            )
        elif not args.dry_run:
            sheets.upsert_issue(updated_issue)
            sheets.append_alert_log(
                [
                    f"alert-{uuid.uuid4().hex[:12]}",
                    updated_issue.issue_id,
                    "suppressed",
                    now_iso,
                    decision.rolling_window_count,
                    decision.new_since_last_alert,
                    "",
                    "",
                    decision.reason,
                ]
            )

        matched_rows = [
            [
                run_id,
                updated_issue.issue_id,
                report.helpscout_url,
                report.date_submitted.isoformat(),
                report.platform,
                report.report_summary,
                now_iso,
                cluster.match_type,
                cluster.confidence,
            ]
            for report in cluster_reports
        ]
        if not args.dry_run:
            sheets.append_matched_report_logs(matched_rows)

        planned.append(
            {
                "issue_id": updated_issue.issue_id,
                "summary": updated_issue.issue_summary,
                "status": updated_issue.status,
                "alert_type": decision.alert_type,
                "should_alert": decision.should_alert,
                "reason": decision.reason,
                "rolling_window_count": decision.rolling_window_count,
                "new_since_last_alert": decision.new_since_last_alert,
                "links": list(decision.helpscout_links),
            }
        )

    if args.dry_run:
        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "window": {"start": report_start.isoformat(), "end": report_end.isoformat()},
                    "report_count": len(reports),
                    "cluster_count": len(clusters),
                    "planned_issues": planned,
                },
                indent=2,
            )
        )
    else:
        sent_count = len([item for item in planned if item["should_alert"]])
        LOGGER.info("Processed %s reports into %s clusters; sent %s alerts", len(reports), len(clusters), sent_count)

    return 0


def _parse_run_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=PT, hour=8)


if __name__ == "__main__":
    sys.exit(run())
