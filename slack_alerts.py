from __future__ import annotations

from datetime import date
from urllib.parse import urlparse

from models import AlertDecision


def format_issue_alert(decision: AlertDecision) -> str:
    lines = [
        ":rotating_light: *Possible Recurring Bug Detected*",
        "",
        "*Issue Summary:*",
        decision.issue_summary,
        "",
        "*Report Volume:*",
        f"{decision.rolling_window_count} matching reports in the rolling window",
        f"{decision.new_since_last_alert} new matching reports since the last alert",
        "",
        "*Platforms:*",
    ]
    for platform in ("Android", "iOS", "Apple Watch", "Unknown"):
        count = decision.platforms.get(platform)
        if count:
            lines.append(f"{platform}: {count}")
    for platform, count in sorted(decision.platforms.items()):
        if platform not in {"Android", "iOS", "Apple Watch", "Unknown"}:
            lines.append(f"{platform}: {count}")

    lines.extend(
        [
            "",
            "*First Noticed:*",
            _display_date(decision.first_noticed),
            "",
            "*Latest Report:*",
            _display_date(decision.latest_report),
            "",
            "*Help Scout Links:*",
        ]
    )
    lines.extend(f"* {format_helpscout_reference(link)}" for link in decision.helpscout_links[:10])
    return "\n".join(lines)


def send_slack_message(webhook_url: str, message: str) -> str:
    import requests

    response = requests.post(webhook_url, json={"text": message}, timeout=15)
    response.raise_for_status()
    return ""


def format_helpscout_reference(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "(blank)"
    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        escaped = raw.replace("|", "%7C")
        return f"<{escaped}|{raw}>"
    return raw


def _display_date(value: date) -> str:
    return f"{value.strftime('%B')} {value.day}, {value.year}"
