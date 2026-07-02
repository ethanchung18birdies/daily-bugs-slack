from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from zoneinfo import ZoneInfo


DEFAULT_SOURCE_SPREADSHEET_ID = "19JPqsVsE0hU-oBF5G02HdctrQBgTBudzQvFFyQHaj28"
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
PT = ZoneInfo("America/Los_Angeles")

DEFAULT_HIGH_IMPACT_TERMS = (
    "round saving",
    "finish round",
    "save round",
    "score loss",
    "lost score",
    "app crash",
    "crash",
    "login",
    "subscription access",
    "payment access",
    "tournament scoring",
    "league leaderboard",
    "apple watch score sync",
    "watch score sync",
    "gps wrong",
    "incorrect gps",
    "gps distance",
)


@dataclass(frozen=True)
class Settings:
    product_feedback_spreadsheet_id: str
    issue_memory_spreadsheet_id: str
    google_service_account_json: Path
    slack_webhook_url: str
    slack_bot_token: str
    slack_channel_id: str
    openai_api_key: str
    openai_model: str
    rolling_window_days: int
    new_issue_threshold: int
    high_impact_threshold: int
    existing_update_threshold: int
    patched_alert_threshold: int
    high_impact_terms: tuple[str, ...]
    log_level: str


def load_settings(dotenv_path: str | None = None, *, require_slack: bool = True) -> Settings:
    _load_dotenv_if_available(dotenv_path)
    high_impact_terms = tuple(
        term.strip().casefold()
        for term in os.getenv("HIGH_IMPACT_TERMS", "").split(",")
        if term.strip()
    ) or DEFAULT_HIGH_IMPACT_TERMS
    slack_webhook_url = os.getenv("PRODUCT_FEEDBACK_SLACK_WEBHOOK_URL", "")
    slack_bot_token = os.getenv("SLACK_BOT_TOKEN", "")
    slack_channel_id = os.getenv("SLACK_CHANNEL_ID", "")
    if require_slack and not slack_webhook_url and not (slack_bot_token and slack_channel_id):
        raise ValueError(
            "Missing Slack configuration: set SLACK_BOT_TOKEN and SLACK_CHANNEL_ID, "
            "or set PRODUCT_FEEDBACK_SLACK_WEBHOOK_URL for legacy webhook fallback"
        )

    return Settings(
        product_feedback_spreadsheet_id=os.getenv(
            "PRODUCT_FEEDBACK_SPREADSHEET_ID", DEFAULT_SOURCE_SPREADSHEET_ID
        ),
        issue_memory_spreadsheet_id=_required_env("ISSUE_MEMORY_SPREADSHEET_ID"),
        google_service_account_json=Path(_required_env("GOOGLE_SERVICE_ACCOUNT_JSON")).expanduser(),
        slack_webhook_url=slack_webhook_url,
        slack_bot_token=slack_bot_token,
        slack_channel_id=slack_channel_id,
        openai_api_key=_required_env("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        rolling_window_days=_int_env("ROLLING_WINDOW_DAYS", 7),
        new_issue_threshold=_int_env("NEW_ISSUE_THRESHOLD", 3),
        high_impact_threshold=_int_env("HIGH_IMPACT_THRESHOLD", 2),
        existing_update_threshold=_int_env("EXISTING_UPDATE_THRESHOLD", 3),
        patched_alert_threshold=_int_env("PATCHED_ALERT_THRESHOLD", 2),
        high_impact_terms=high_impact_terms,
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _load_dotenv_if_available(dotenv_path: str | None) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(dotenv_path=dotenv_path)
