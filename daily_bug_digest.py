from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import logging
import os
from pathlib import Path
import re
import sys
from typing import Iterable
from urllib.parse import urlparse
from zoneinfo import ZoneInfo


DEFAULT_SPREADSHEET_ID = "19JPqsVsE0hU-oBF5G02HdctrQBgTBudzQvFFyQHaj28"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
PT = ZoneInfo("America/Los_Angeles")
EXPECTED_COLUMNS = (
    "HelpScout Url",
    "Category",
    "Feedback",
    "Date Submitted",
    "Next Step",
    "Check CS Response",
)

LOGGER = logging.getLogger("daily_slack_bugs")


@dataclass(frozen=True)
class Settings:
    spreadsheet_id: str
    google_service_account_json: Path
    slack_webhook_url: str
    log_level: str


@dataclass(frozen=True)
class FeedbackRow:
    tab_name: str
    row_number: int
    helpscout_url: str
    category: str
    feedback: str
    date_submitted_raw: str
    next_step: str
    check_cs_response: str


@dataclass(frozen=True)
class CleanedFeedback:
    content: str
    user_type: str | None
    device_type: str | None
    app_version: str | None


def load_settings(dotenv_path: str | None = None, *, require_slack: bool = True) -> Settings:
    _load_dotenv_if_available(dotenv_path)
    service_account_path = _required_env("GOOGLE_SERVICE_ACCOUNT_JSON")
    slack_webhook_url = (
        _required_env("PRODUCT_FEEDBACK_SLACK_WEBHOOK_URL")
        if require_slack
        else os.getenv("PRODUCT_FEEDBACK_SLACK_WEBHOOK_URL", "")
    )
    return Settings(
        spreadsheet_id=os.getenv("PRODUCT_FEEDBACK_SPREADSHEET_ID", DEFAULT_SPREADSHEET_ID),
        google_service_account_json=Path(service_account_path).expanduser(),
        slack_webhook_url=slack_webhook_url,
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )


def configure_logging(level_name: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level_name.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def previous_report_date(now: datetime | None = None) -> date:
    if now is None:
        now = datetime.now(PT)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=PT)
    else:
        now = now.astimezone(PT)
    return now.date() - timedelta(days=1)


def month_tab_name(report_date: date) -> str:
    return report_date.strftime("%B")


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


def rows_from_values(tab_name: str, values: list[list[str]]) -> list[FeedbackRow]:
    if not values:
        LOGGER.warning("Tab %s is empty", tab_name)
        return []

    headers = [header.strip() for header in values[0]]
    missing = [column for column in EXPECTED_COLUMNS if column not in headers]
    if missing:
        raise ValueError(f"Tab {tab_name} is missing required columns: {', '.join(missing)}")

    rows: list[FeedbackRow] = []
    for row_number, raw_row in enumerate(values[1:], start=2):
        record = _record_from_row(headers, raw_row)
        rows.append(
            FeedbackRow(
                tab_name=tab_name,
                row_number=row_number,
                helpscout_url=record.get("HelpScout Url", "").strip(),
                category=record.get("Category", "").strip(),
                feedback=record.get("Feedback", "").strip(),
                date_submitted_raw=record.get("Date Submitted", "").strip(),
                next_step=record.get("Next Step", "").strip(),
                check_cs_response=record.get("Check CS Response", "").strip(),
            )
        )
    return rows


def filter_daily_bugs(rows: Iterable[FeedbackRow], report_date: date) -> list[FeedbackRow]:
    bugs: list[FeedbackRow] = []
    for row in rows:
        if row.category.casefold() != "bug":
            continue

        parsed_date = parse_sheet_date(row.date_submitted_raw)
        if parsed_date is None:
            LOGGER.warning(
                "Skipping bug row with invalid date: tab=%s row=%s raw_date=%r",
                row.tab_name,
                row.row_number,
                row.date_submitted_raw,
            )
            continue

        if parsed_date == report_date:
            bugs.append(row)
    return bugs


def format_slack_message(bugs: list[FeedbackRow], report_date: date) -> str:
    report_label = display_report_date(report_date)
    header = f"Daily CS Product Bugs: {len(bugs)} from {report_label}"
    if not bugs:
        return header

    lines = [f"*{header}*"]
    for index, bug in enumerate(bugs, start=1):
        cleaned = clean_feedback(bug.feedback)
        if index > 1:
            lines.extend(["", "==="])
        lines.extend(
            [
                "",
                f"*{index}. HelpScout:* {format_helpscout_reference(bug.helpscout_url)}",
            ]
        )
        metadata = format_metadata(cleaned)
        if metadata:
            lines.append(f"*Metadata:* {metadata}")
        lines.append(f"*Feedback:*\n{cleaned.content or '(blank)'}")
        if bug.next_step:
            lines.append(f"*Next Step:* {bug.next_step}")
    return "\n".join(lines)


def clean_feedback(feedback: str) -> CleanedFeedback:
    raw = (feedback or "").strip()
    feedback_match = _last_feedback_marker(raw)
    if feedback_match is None:
        return clean_beacon_feedback(raw)

    content = raw[feedback_match.end() :].strip()
    premium_match = re.search(r"(?im)^Is premiumUser:\s*(true|false)\s*$", raw)
    device_match = re.search(r"(?im)^Device:\s*(.+?)\s*$", raw)

    user_type = None
    if premium_match:
        user_type = "Premium User" if premium_match.group(1).casefold() == "true" else "Standard User"

    device_type = None
    app_version = None
    if device_match:
        device_line = device_match.group(1).strip()
        device_type = "iOS" if "ios" in device_line.casefold() else "Android"
        versions = re.findall(r"\b\d+\.\d+\.\d+\b", device_line)
        if versions:
            app_version = versions[-1]

    return CleanedFeedback(
        content=content,
        user_type=user_type,
        device_type=device_type,
        app_version=app_version,
    )


def clean_beacon_feedback(feedback: str) -> CleanedFeedback:
    raw = (feedback or "").strip().strip('"')
    beacon_match = _last_beacon_opened_marker(raw)
    if beacon_match is None:
        return CleanedFeedback(content=(feedback or "").strip(), user_type=None, device_type=None, app_version=None)

    content = raw[beacon_match.end() :].strip()
    if not content:
        content = _content_before_technical_info(raw) or raw
    device_type = extract_beacon_device_type(raw)
    return CleanedFeedback(
        content=content,
        user_type=None,
        device_type=device_type,
        app_version=None,
    )


def extract_beacon_device_type(feedback: str) -> str | None:
    operating_system = _line_value(feedback, "Operating System")
    device = _line_value(feedback, "Device")
    browser_version = _line_value(feedback, "Browser/Version")
    device_text = " ".join(
        value for value in (operating_system, device, browser_version) if value
    )
    if not device_text:
        return None
    return "iOS" if "ios" in device_text.casefold() else "Android"


def format_metadata(cleaned: CleanedFeedback) -> str:
    parts = [
        part
        for part in (cleaned.user_type, cleaned.device_type, cleaned.app_version)
        if part
    ]
    return " | ".join(parts)


def format_helpscout_reference(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "(blank)"
    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        escaped = raw.replace("|", "%7C")
        return f"<{escaped}|{raw}>"
    return raw


def fetch_sheet_rows(settings: Settings, tab_name: str) -> list[FeedbackRow]:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        settings.google_service_account_json,
        scopes=SCOPES,
    )
    service = build("sheets", "v4", credentials=creds, cache_discovery=False)
    response = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=settings.spreadsheet_id,
            range=f"'{tab_name}'!A:Z",
        )
        .execute()
    )
    return rows_from_values(tab_name, response.get("values", []))


def send_slack_message(webhook_url: str, message: str) -> None:
    import requests

    response = requests.post(webhook_url, json={"text": message}, timeout=15)
    response.raise_for_status()


def rows_from_csv(path: Path, tab_name: str) -> list[FeedbackRow]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        values = list(reader)
    return rows_from_values(tab_name, values)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send the daily CS product bug Slack digest.")
    parser.add_argument("--dotenv", help="Path to a .env file. Defaults to .env in the current directory.")
    parser.add_argument("--dry-run", action="store_true", help="Print the Slack message without posting it.")
    parser.add_argument("--run-date", help="Pretend the job is running on this PT date, in YYYY-MM-DD format.")
    parser.add_argument("--csv", type=Path, help="Read rows from a local CSV export instead of Google Sheets.")
    args = parser.parse_args(argv)

    dotenv_path = args.dotenv or ".env"
    _load_dotenv_if_available(dotenv_path)
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))

    now = _parse_run_date(args.run_date) if args.run_date else datetime.now(PT)
    report_date = previous_report_date(now)
    tab_name = month_tab_name(report_date)

    if args.csv:
        rows = rows_from_csv(args.csv, tab_name)
    else:
        settings = load_settings(dotenv_path=dotenv_path, require_slack=not args.dry_run)
        configure_logging(settings.log_level)
        rows = fetch_sheet_rows(settings, tab_name)

    bugs = filter_daily_bugs(rows, report_date)
    message = format_slack_message(bugs, report_date)

    if args.dry_run:
        print(message)
    else:
        settings = load_settings(dotenv_path=dotenv_path)
        send_slack_message(settings.slack_webhook_url, message)
        LOGGER.info("Sent daily bug digest with %s bugs for %s", len(bugs), report_date)

    return 0


def _record_from_row(headers: list[str], row: list[str]) -> dict[str, str]:
    padded = row + [""] * (len(headers) - len(row))
    return {header: padded[index] for index, header in enumerate(headers)}


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _parse_run_date(value: str) -> datetime:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("--run-date must use YYYY-MM-DD")
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=PT, hour=8)


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


def _content_before_technical_info(value: str) -> str | None:
    match = re.search(r"(?im)\bTechnical Information\s*(?:\n|$)", value)
    if not match:
        return None
    content = value[: match.start()].strip()
    return content or None


def _load_dotenv_if_available(dotenv_path: str | None) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        if dotenv_path and Path(dotenv_path).exists():
            LOGGER.warning("python-dotenv is not installed; ignoring %s", dotenv_path)
        return

    load_dotenv(dotenv_path=dotenv_path)


if __name__ == "__main__":
    sys.exit(run())
