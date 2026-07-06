from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CleanedFeedback:
    content: str
    user_type: str | None
    device_type: str | None
    app_version: str | None
    user_id: str | None = None
    tags: str | None = None
    club_id: str | None = None
    course_or_club_name: str | None = None
    device: str | None = None


@dataclass(frozen=True)
class SourceReport:
    source_tab: str
    row_number: int
    helpscout_url: str
    category: str
    feedback_raw: str
    date_submitted: date
    cleaned_feedback: CleanedFeedback
    platform: str
    report_summary: str


@dataclass(frozen=True)
class IssueRecord:
    issue_id: str
    status: str
    issue_summary: str
    feature_area: str
    platforms: str
    first_noticed: str
    latest_report: str
    rolling_window_count: int
    new_since_last_alert: int
    total_report_count: int
    helpscout_links: str
    last_slack_alert_sent: str
    patch_date: str
    close_date: str
    owner: str
    engineering_link: str
    notes: str
    created_at: str
    updated_at: str
    issue_signature: str
    slack_channel_id: str = ""
    slack_message_ts: str = ""
    slack_message_url: str = ""
    last_slack_update_sent: str = ""
    acknowledged_at: str = ""
    acknowledged_by: str = ""
    resolved_at: str = ""
    resolved_by: str = ""
    slack_message_deleted_at: str = ""
    slack_message_deleted_by: str = ""
    last_slack_reminder_sent: str = ""
    reminder_report_count: int = 0
    row_number: int | None = None


@dataclass(frozen=True)
class IssueCluster:
    issue_id: str | None
    issue_summary: str
    feature_area: str
    issue_signature: str
    report_indices: tuple[int, ...]
    match_type: str
    confidence: float


@dataclass(frozen=True)
class AlertDecision:
    issue_id: str
    alert_type: str
    should_alert: bool
    reason: str
    rolling_window_count: int
    new_since_last_alert: int
    reports: tuple[SourceReport, ...]
    issue_summary: str
    platforms: dict[str, int]
    first_noticed: date
    latest_report: date
    helpscout_links: tuple[str, ...]
    slack_action: str = "none"
