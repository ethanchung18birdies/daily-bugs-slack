from __future__ import annotations

from datetime import date
from dataclasses import dataclass
from urllib.parse import urlparse

from models import AlertDecision, IssueRecord


@dataclass(frozen=True)
class SlackMessageResult:
    channel_id: str
    message_ts: str
    message_url: str


@dataclass(frozen=True)
class SlackReaction:
    name: str
    users: tuple[str, ...]
    count: int


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


def build_issue_alert_payload(issue: IssueRecord, decision: AlertDecision) -> dict:
    text = f"{issue.status}: {decision.issue_summary} ({decision.rolling_window_count} reports)"
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Recurring Bug Alert", "emoji": True},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Status:*\n{_escape_mrkdwn(issue.status)}"},
                {"type": "mrkdwn", "text": f"*Issue ID:*\n{_escape_mrkdwn(issue.issue_id)}"},
            ],
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Issue Summary:*\n{_escape_mrkdwn(decision.issue_summary)}"}},
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": (
                        "*Report Volume:*\n"
                        f"{decision.rolling_window_count} in window\n"
                        f"{decision.new_since_last_alert} new since last update"
                    ),
                },
                {
                    "type": "mrkdwn",
                    "text": (
                        "*Dates:*\n"
                        f"First: {_display_date(decision.first_noticed)}\n"
                        f"Latest: {_display_date(decision.latest_report)}"
                    ),
                },
            ],
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Platforms:*\n{_format_platforms(decision.platforms)}"}},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Help Scout Links:*\n{_format_helpscout_links(decision.helpscout_links)}",
            },
        },
    ]
    if issue.status != "Resolved":
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "React with :eyes: to acknowledge or :white_check_mark: to resolve.",
                    }
                ],
            }
        )
    return {"text": text, "blocks": blocks, "unfurl_links": False, "unfurl_media": False}


def send_slack_message(webhook_url: str, message: str) -> str:
    import requests

    response = requests.post(webhook_url, json={"text": message}, timeout=15)
    response.raise_for_status()
    return ""


def post_issue_alert(bot_token: str, channel_id: str, issue: IssueRecord, decision: AlertDecision) -> SlackMessageResult:
    payload = {"channel": channel_id, **build_issue_alert_payload(issue, decision)}
    response = _slack_api_call(bot_token, "chat.postMessage", payload)
    response_channel = response.get("channel", channel_id)
    message_ts = response["ts"]
    return SlackMessageResult(
        channel_id=response_channel,
        message_ts=message_ts,
        message_url=get_message_permalink(bot_token, response_channel, message_ts),
    )


def update_issue_alert(bot_token: str, channel_id: str, message_ts: str, issue: IssueRecord, decision: AlertDecision) -> SlackMessageResult:
    payload = {"channel": channel_id, "ts": message_ts, **build_issue_alert_payload(issue, decision)}
    response = _slack_api_call(bot_token, "chat.update", payload)
    response_channel = response.get("channel", channel_id)
    response_ts = response.get("ts", message_ts)
    return SlackMessageResult(
        channel_id=response_channel,
        message_ts=response_ts,
        message_url=get_message_permalink(bot_token, response_channel, response_ts),
    )


def get_message_permalink(bot_token: str, channel_id: str, message_ts: str) -> str:
    response = _slack_api_call(bot_token, "chat.getPermalink", {"channel": channel_id, "message_ts": message_ts})
    return response.get("permalink", "")


def get_message_reactions(bot_token: str, channel_id: str, message_ts: str) -> tuple[SlackReaction, ...]:
    response = _slack_api_get(
        bot_token,
        "reactions.get",
        {"channel": channel_id, "timestamp": message_ts, "full": True},
    )
    message = response.get("message", {})
    return tuple(
        SlackReaction(
            name=str(reaction.get("name", "")),
            users=tuple(str(user) for user in reaction.get("users", [])),
            count=int(reaction.get("count", 0) or 0),
        )
        for reaction in message.get("reactions", [])
        if reaction.get("name")
    )


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


def _slack_api_call(bot_token: str, method: str, payload: dict) -> dict:
    import requests

    response = requests.post(
        f"https://slack.com/api/{method}",
        headers={"Authorization": f"Bearer {bot_token}", "Content-Type": "application/json; charset=utf-8"},
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack API {method} failed: {data.get('error', 'unknown_error')}")
    return data


def _slack_api_get(bot_token: str, method: str, params: dict) -> dict:
    import requests

    response = requests.get(
        f"https://slack.com/api/{method}",
        headers={"Authorization": f"Bearer {bot_token}"},
        params=params,
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack API {method} failed: {data.get('error', 'unknown_error')}")
    return data


def _format_platforms(platforms: dict[str, int]) -> str:
    lines = []
    for platform in ("Android", "iOS", "Apple Watch", "Unknown"):
        count = platforms.get(platform)
        if count:
            lines.append(f"{_escape_mrkdwn(platform)}: {count}")
    for platform, count in sorted(platforms.items()):
        if platform not in {"Android", "iOS", "Apple Watch", "Unknown"}:
            lines.append(f"{_escape_mrkdwn(platform)}: {count}")
    return "\n".join(lines) or "Unknown"


def _format_helpscout_links(links: tuple[str, ...]) -> str:
    if not links:
        return "No Help Scout links found"
    rendered = [f"* {format_helpscout_reference(link)}" for link in links[:10]]
    if len(links) > 10:
        rendered.append(f"* +{len(links) - 10} more in Issue Memory")
    return "\n".join(rendered)


def _escape_mrkdwn(value: str) -> str:
    return (value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
