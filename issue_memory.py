from __future__ import annotations

from collections import Counter
from datetime import date, datetime
import hashlib
from typing import Iterable

from models import IssueCluster, IssueRecord, SourceReport


ISSUE_STATUSES = ("Monitoring", "Open", "Escalated", "Patched", "Closed", "Dismissed")
ISSUE_MEMORY_COLUMNS = (
    "issue_id",
    "status",
    "issue_summary",
    "feature_area",
    "platforms",
    "first_noticed",
    "latest_report",
    "rolling_window_count",
    "new_since_last_alert",
    "total_report_count",
    "helpscout_links",
    "last_slack_alert_sent",
    "patch_date",
    "close_date",
    "owner",
    "engineering_link",
    "notes",
    "created_at",
    "updated_at",
    "issue_signature",
)

ALERT_LOG_COLUMNS = (
    "alert_id",
    "issue_id",
    "alert_type",
    "sent_at",
    "rolling_window_count",
    "new_since_last_alert",
    "slack_channel",
    "slack_message_ts",
    "notes",
)

MATCHED_REPORTS_COLUMNS = (
    "run_id",
    "issue_id",
    "helpscout_url",
    "date_submitted",
    "platform",
    "report_summary",
    "matched_at",
    "match_type",
    "confidence",
)


def issue_from_row(row: dict[str, str], row_number: int | None = None) -> IssueRecord:
    return IssueRecord(
        issue_id=row.get("issue_id", "").strip(),
        status=row.get("status", "Monitoring").strip() or "Monitoring",
        issue_summary=row.get("issue_summary", "").strip(),
        feature_area=row.get("feature_area", "").strip(),
        platforms=row.get("platforms", "").strip(),
        first_noticed=row.get("first_noticed", "").strip(),
        latest_report=row.get("latest_report", "").strip(),
        rolling_window_count=_int(row.get("rolling_window_count", "")),
        new_since_last_alert=_int(row.get("new_since_last_alert", "")),
        total_report_count=_int(row.get("total_report_count", "")),
        helpscout_links=row.get("helpscout_links", "").strip(),
        last_slack_alert_sent=row.get("last_slack_alert_sent", "").strip(),
        patch_date=row.get("patch_date", "").strip(),
        close_date=row.get("close_date", "").strip(),
        owner=row.get("owner", "").strip(),
        engineering_link=row.get("engineering_link", "").strip(),
        notes=row.get("notes", "").strip(),
        created_at=row.get("created_at", "").strip(),
        updated_at=row.get("updated_at", "").strip(),
        issue_signature=row.get("issue_signature", "").strip(),
        row_number=row_number,
    )


def issue_to_row(issue: IssueRecord) -> list[str | int]:
    return [
        issue.issue_id,
        issue.status,
        issue.issue_summary,
        issue.feature_area,
        issue.platforms,
        issue.first_noticed,
        issue.latest_report,
        issue.rolling_window_count,
        issue.new_since_last_alert,
        issue.total_report_count,
        issue.helpscout_links,
        issue.last_slack_alert_sent,
        issue.patch_date,
        issue.close_date,
        issue.owner,
        issue.engineering_link,
        issue.notes,
        issue.created_at,
        issue.updated_at,
        issue.issue_signature,
    ]


def build_updated_issue(
    cluster: IssueCluster,
    reports: list[SourceReport],
    existing: IssueRecord | None,
    now_iso: str,
) -> IssueRecord:
    first = min(report.date_submitted for report in reports)
    latest = max(report.date_submitted for report in reports)
    links = sorted({report.helpscout_url for report in reports if report.helpscout_url})
    existing_links = _split_lines(existing.helpscout_links) if existing else []
    all_links = sorted(set(existing_links).union(links))
    platforms = format_platform_counts(Counter(report.platform for report in reports))
    last_alert_date = _date_part(existing.last_slack_alert_sent) if existing else None
    existing_first = _safe_parse_date(existing.first_noticed) if existing else None
    existing_latest = _safe_parse_date(existing.latest_report) if existing else None

    new_since_last_alert = (
        len([report for report in reports if not last_alert_date or report.date_submitted > last_alert_date])
        if existing
        else len(reports)
    )

    issue_id = existing.issue_id if existing else make_issue_id(cluster.issue_signature, first)
    return IssueRecord(
        issue_id=issue_id,
        status=existing.status if existing else "Monitoring",
        issue_summary=cluster.issue_summary,
        feature_area=cluster.feature_area,
        platforms=platforms,
        first_noticed=min(existing_first or first, first).isoformat(),
        latest_report=max(existing_latest or latest, latest).isoformat(),
        rolling_window_count=len(reports),
        new_since_last_alert=new_since_last_alert,
        total_report_count=max(existing.total_report_count if existing else 0, len(existing_links)) + len(
            [link for link in links if link not in existing_links]
        ),
        helpscout_links="\n".join(all_links),
        last_slack_alert_sent=existing.last_slack_alert_sent if existing else "",
        patch_date=existing.patch_date if existing else "",
        close_date=existing.close_date if existing else "",
        owner=existing.owner if existing else "",
        engineering_link=existing.engineering_link if existing else "",
        notes=existing.notes if existing else "",
        created_at=existing.created_at if existing and existing.created_at else now_iso,
        updated_at=now_iso,
        issue_signature=cluster.issue_signature,
        row_number=existing.row_number if existing else None,
    )


def mark_alert_sent(issue: IssueRecord, sent_at: str) -> IssueRecord:
    return IssueRecord(
        **{**issue.__dict__, "last_slack_alert_sent": sent_at, "updated_at": sent_at}
    )


def format_platform_counts(counts: Counter[str]) -> str:
    ordered = ["Android", "iOS", "Apple Watch", "Unknown"]
    parts = [f"{platform}: {counts[platform]}" for platform in ordered if counts.get(platform)]
    parts.extend(f"{platform}: {count}" for platform, count in sorted(counts.items()) if platform not in ordered)
    return "\n".join(parts)


def make_issue_id(signature: str, first_noticed: date) -> str:
    digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:8]
    return f"ISSUE-{first_noticed.strftime('%Y%m%d')}-{digest}"


def find_existing_issue(cluster: IssueCluster, issues: Iterable[IssueRecord]) -> IssueRecord | None:
    active = [issue for issue in issues if issue.status not in {"Closed", "Dismissed"}]
    if cluster.issue_id:
        for issue in active:
            if issue.issue_id == cluster.issue_id:
                return issue
    for issue in active:
        if issue.issue_signature and issue.issue_signature == cluster.issue_signature:
            return issue
    return None


def _int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _split_lines(value: str) -> list[str]:
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


def _safe_parse_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def _date_part(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None
