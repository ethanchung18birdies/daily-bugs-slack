from __future__ import annotations

from datetime import date, datetime, timedelta
import re
from typing import Iterable

from config import PT
from models import CleanedFeedback, SourceReport


SOURCE_COLUMNS = (
    "HelpScout Url",
    "Category",
    "Feedback",
    "Date Submitted",
)

OPTIONAL_SOURCE_COLUMNS = (
    "Next Step",
    "Check CS Response",
)

BUG_LANGUAGE = re.compile(
    r"\b("
    r"bug|broken|crash(?:es|ed|ing)?|freeze|freezes|frozen|stuck|spinner|loading|"
    r"cannot|can't|unable|won't|does not|doesn't|not saving|not save|not syncing|"
    r"lost|missing|incorrect|wrong|error|failed|fails|locked|loop"
    r")\b",
    re.IGNORECASE,
)


def previous_report_date(now: datetime | None = None) -> date:
    if now is None:
        now = datetime.now(PT)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=PT)
    else:
        now = now.astimezone(PT)
    return now.date() - timedelta(days=1)


def rolling_window(report_end: date, days: int) -> tuple[date, date]:
    return report_end - timedelta(days=days - 1), report_end


def month_tab_name(report_date: date) -> str:
    return report_date.strftime("%B")


def month_tabs_for_window(start: date, end: date) -> list[str]:
    tabs: list[str] = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        tab = month_tab_name(cursor)
        if tab not in tabs:
            tabs.append(tab)
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return tabs


def display_report_date(report_date: date) -> str:
    return f"{report_date.strftime('%B')} {report_date.day}"


def parse_sheet_date(value: str) -> date | None:
    raw = (value or "").strip()
    if not raw:
        return None

    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%-m/%-d/%y", "%-m/%-d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue

    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed.date()
        except ValueError:
            continue

    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.date()
    return parsed.astimezone(PT).date()


def parse_source_rows(tab_name: str, values: list[list[str]], start: date, end: date) -> list[SourceReport]:
    if not values:
        return []
    headers = [header.strip() for header in values[0]]
    missing = [column for column in SOURCE_COLUMNS if column not in headers]
    if missing:
        raise ValueError(f"Tab {tab_name} is missing required columns: {', '.join(missing)}")

    reports: list[SourceReport] = []
    for row_number, raw_row in enumerate(values[1:], start=2):
        record = _record_from_row(headers, raw_row)
        category = record.get("Category", "").strip()
        raw_feedback = record.get("Feedback", "").strip()
        submitted = parse_sheet_date(record.get("Date Submitted", ""))
        if submitted is None or not (start <= submitted <= end):
            continue

        cleaned = clean_feedback(raw_feedback)
        if not should_include_report(category, cleaned.content):
            continue

        platform = infer_platform(cleaned, raw_feedback)
        reports.append(
            SourceReport(
                source_tab=tab_name,
                row_number=row_number,
                helpscout_url=record.get("HelpScout Url", "").strip(),
                category=category,
                feedback_raw=raw_feedback,
                date_submitted=submitted,
                cleaned_feedback=cleaned,
                platform=platform,
                report_summary=summarize_report(cleaned.content),
            )
        )
    return reports


def should_include_report(category: str, cleaned_feedback: str) -> bool:
    if category.strip().casefold() == "bug":
        return True
    return bool(BUG_LANGUAGE.search(cleaned_feedback or ""))


def summarize_report(content: str, max_chars: int = 220) -> str:
    cleaned = re.sub(r"\s+", " ", (content or "").strip())
    if not cleaned:
        return ""
    first_sentence = re.split(r"(?<=[.!?])\s+", cleaned, maxsplit=1)[0]
    summary = first_sentence if len(first_sentence) >= 35 else cleaned
    return summary[: max_chars - 1].rstrip() + "…" if len(summary) > max_chars else summary


def clean_feedback(feedback: str) -> CleanedFeedback:
    raw = (feedback or "").strip()
    feedback_match = _last_feedback_marker(raw)
    if feedback_match is None:
        return clean_beacon_feedback(raw)

    content = raw[feedback_match.end() :].strip()
    premium_match = re.search(r"(?im)^Is premiumUser:\s*(true|false)\s*$", raw)
    device_line = _labeled_value(raw, "Device")

    user_type = None
    if premium_match:
        user_type = "Premium User" if premium_match.group(1).casefold() == "true" else "Standard User"

    app_version = extract_app_version(device_line or "")
    return CleanedFeedback(
        content=content,
        user_type=user_type,
        device_type=infer_platform_from_text(device_line or ""),
        app_version=app_version,
        user_id=_labeled_value(raw, "UserId"),
        tags=_labeled_value(raw, "Tags"),
        club_id=_labeled_value(raw, "Club id"),
        course_or_club_name=_extract_course_or_club_name(raw),
        device=device_line,
    )


def clean_beacon_feedback(feedback: str) -> CleanedFeedback:
    raw = (feedback or "").strip().strip('"')
    beacon_match = _last_beacon_opened_marker(raw)
    if beacon_match is None:
        return CleanedFeedback(content=(feedback or "").strip(), user_type=None, device_type=None, app_version=None)

    content = raw[beacon_match.end() :].strip()
    if not content:
        content = _content_before_technical_info(raw) or raw
    device_text = " ".join(
        value
        for value in (
            _line_value(raw, "Operating System"),
            _line_value(raw, "Device"),
            _line_value(raw, "Browser/Version"),
        )
        if value
    )
    return CleanedFeedback(
        content=content,
        user_type=None,
        device_type=infer_platform_from_text(device_text),
        app_version=extract_app_version(device_text),
        device=_line_value(raw, "Device"),
    )


def infer_platform(cleaned: CleanedFeedback, raw_feedback: str = "") -> str:
    parts = [
        cleaned.device_type or "",
        cleaned.device or "",
        cleaned.content or "",
        raw_feedback or "",
    ]
    return infer_platform_from_text(" ".join(parts)) or "Unknown"


def infer_platform_from_text(value: str) -> str | None:
    text = (value or "").casefold()
    if not text:
        return None
    if "apple watch" in text or "watchos" in text:
        return "Apple Watch"
    if "iphone" in text or "ios" in text or "ipad" in text:
        return "iOS"
    if "android" in text or "pixel" in text or "samsung" in text or re.search(r"\bsm-[a-z0-9]", text):
        return "Android"
    return None


def extract_app_version(value: str) -> str | None:
    versions = re.findall(r"\b\d+\.\d+\.\d+\b", value or "")
    return versions[-1] if versions else None


def normalize_signature_text(value: str) -> str:
    text = re.sub(r"[^a-z0-9\s]", " ", (value or "").casefold())
    tokens = [token for token in text.split() if len(token) > 2]
    stop = {"the", "and", "for", "with", "that", "this", "when", "have", "from", "app", "birdies"}
    return " ".join(token for token in tokens if token not in stop)


def _record_from_row(headers: list[str], row: list[str]) -> dict[str, str]:
    padded = row + [""] * (len(headers) - len(row))
    return {header: padded[index] for index, header in enumerate(headers)}


def _last_feedback_marker(value: str) -> re.Match[str] | None:
    matches = list(re.finditer(r"(?im)^Feedback:\s*", value))
    if matches:
        return matches[-1]
    inline_matches = list(re.finditer(r"(?i)\bFeedback:\s*", value))
    return inline_matches[-1] if inline_matches else None


def _last_beacon_opened_marker(value: str) -> re.Match[str] | None:
    matches = list(re.finditer(r"(?im)^Beacon opened on .*(?:\n|$)", value))
    return matches[-1] if matches else None


def _line_value(value: str, label: str) -> str | None:
    escaped = re.escape(label)
    match = re.search(rf"(?im)^{escaped}\s*\n(.+?)\s*$", value)
    return match.group(1).strip() if match else None


def _labeled_value(value: str, label: str) -> str | None:
    escaped = re.escape(label)
    match = re.search(rf"(?im)^{escaped}:\s*(.+?)\s*$", value)
    return match.group(1).strip() if match else None


def _content_before_technical_info(value: str) -> str | None:
    match = re.search(r"(?im)\bTechnical Information\s*(?:\n|$)", value)
    if not match:
        return None
    content = value[: match.start()].strip()
    return content or None


def _extract_course_or_club_name(value: str) -> str | None:
    nearest = _labeled_value(value, "Nearest course name")
    club = _labeled_value(value, "Club name")
    return nearest or club
