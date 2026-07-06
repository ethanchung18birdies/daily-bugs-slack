from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone

from config import Settings
from models import AlertDecision, IssueRecord, SourceReport


def decide_alert(
    *,
    issue: IssueRecord,
    reports: list[SourceReport],
    existing_issue: IssueRecord | None,
    settings: Settings,
) -> AlertDecision:
    platforms = Counter(report.platform for report in reports)
    first_noticed = min(report.date_submitted for report in reports)
    latest_report = max(report.date_submitted for report in reports)
    links = tuple(report.helpscout_url for report in reports if report.helpscout_url)

    alert_type = "none"
    should_alert = False
    reason = "threshold_not_met"

    if issue.status in {"Resolved", "Closed", "Dismissed"}:
        reason = f"issue_status_{issue.status.casefold()}"
        alert_type = "suppressed"
    elif _should_send_stale_reminder(issue):
        alert_type = "stale_unresolved_reminder"
        should_alert = True
        reason = "unresolved_issue_stale_with_new_reports"
    elif issue.status == "Patched" and issue.patch_date:
        post_patch_count = _reports_after(issue.patch_date, reports)
        if post_patch_count >= settings.patched_alert_threshold:
            alert_type = "patched_regression"
            should_alert = True
            reason = "patched_issue_threshold_met"
        else:
            reason = "patched_issue_threshold_not_met"
    elif existing_issue is not None and existing_issue.slack_message_ts:
        if issue.new_since_last_alert > 0:
            alert_type = "existing_issue_update"
            should_alert = True
            reason = "existing_issue_new_reports"
        else:
            reason = "existing_issue_no_new_reports"
    elif existing_issue is not None and existing_issue.last_slack_alert_sent:
        alert_type = "suppressed"
        reason = "existing_issue_already_alerted_without_slack_ts"
    else:
        threshold = settings.high_impact_threshold if is_high_impact(issue, reports, settings) else settings.new_issue_threshold
        if issue.rolling_window_count >= threshold:
            alert_type = "new_issue"
            should_alert = True
            reason = "new_issue_threshold_met"
        else:
            reason = "new_issue_threshold_not_met"

    return AlertDecision(
        issue_id=issue.issue_id,
        alert_type=alert_type,
        should_alert=should_alert,
        reason=reason,
        rolling_window_count=issue.rolling_window_count,
        new_since_last_alert=issue.new_since_last_alert,
        reports=tuple(reports),
        issue_summary=issue.issue_summary,
        platforms=dict(platforms),
        first_noticed=first_noticed,
        latest_report=latest_report,
        helpscout_links=links,
        slack_action=_slack_action(issue, should_alert, reason),
    )


def is_high_impact(issue: IssueRecord, reports: list[SourceReport], settings: Settings) -> bool:
    haystack = " ".join(
        [issue.issue_summary, issue.feature_area]
        + [report.cleaned_feedback.content for report in reports]
    ).casefold()
    return any(term in haystack for term in settings.high_impact_terms)


def _reports_after(patch_date: str, reports: list[SourceReport]) -> int:
    try:
        parsed_patch_date = datetime.fromisoformat(patch_date).date()
    except ValueError:
        return 0
    return len([report for report in reports if report.date_submitted > parsed_patch_date])


def _slack_action(issue: IssueRecord, should_alert: bool, reason: str) -> str:
    if reason == "issue_status_resolved":
        return "suppress_resolved"
    if reason.startswith("issue_status_"):
        return "suppress_status"
    if not should_alert:
        return "none"
    if reason == "unresolved_issue_stale_with_new_reports":
        return "post_reminder"
    if issue.slack_channel_id and issue.slack_message_ts:
        return "update_existing"
    return "post_new"


def _should_send_stale_reminder(issue: IssueRecord) -> bool:
    if issue.status in {"Resolved", "Closed", "Dismissed", "Patched"}:
        return False
    first_alert = _datetime_part(issue.last_slack_alert_sent)
    if not first_alert:
        return False
    if issue.last_slack_reminder_sent and issue.total_report_count <= issue.reminder_report_count:
        return False
    if issue.last_slack_reminder_sent:
        last_reminder = _datetime_part(issue.last_slack_reminder_sent)
        if last_reminder and issue.updated_at and _datetime_part(issue.updated_at) <= last_reminder:
            return False
    age = datetime.now(timezone.utc) - first_alert
    return age.days >= 3


def _datetime_part(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
