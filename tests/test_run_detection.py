from __future__ import annotations

from pathlib import Path
import sys
import types
import unittest

from config import Settings
from models import IssueRecord
from slack_alerts import SlackReaction


google_module = types.ModuleType("google")
google_oauth2_module = types.ModuleType("google.oauth2")
service_account_module = types.ModuleType("google.oauth2.service_account")
service_account_module.Credentials = type("Credentials", (), {"from_service_account_file": staticmethod(lambda *args, **kwargs: object())})
googleapiclient_module = types.ModuleType("googleapiclient")
discovery_module = types.ModuleType("googleapiclient.discovery")
discovery_module.build = lambda *args, **kwargs: object()
errors_module = types.ModuleType("googleapiclient.errors")
errors_module.HttpError = type("HttpError", (Exception,), {})
sys.modules.setdefault("google", google_module)
sys.modules.setdefault("google.oauth2", google_oauth2_module)
sys.modules.setdefault("google.oauth2.service_account", service_account_module)
sys.modules.setdefault("googleapiclient", googleapiclient_module)
sys.modules.setdefault("googleapiclient.discovery", discovery_module)
sys.modules.setdefault("googleapiclient.errors", errors_module)

import run_detection


def settings() -> Settings:
    return Settings(
        product_feedback_spreadsheet_id="source",
        issue_memory_spreadsheet_id="memory",
        google_service_account_json=Path("/tmp/key.json"),
        slack_webhook_url="",
        slack_bot_token="xoxb-token",
        slack_channel_id="C123",
        openai_api_key="key",
        openai_model="model",
        rolling_window_days=7,
        new_issue_threshold=3,
        high_impact_threshold=2,
        existing_update_threshold=3,
        patched_alert_threshold=2,
        high_impact_terms=("finish round", "crash"),
        log_level="INFO",
    )


def issue(**overrides) -> IssueRecord:
    values = dict(
        issue_id="ISSUE-1",
        status="Monitoring",
        issue_summary="Users cannot finish rounds",
        feature_area="Rounds",
        platforms="",
        first_noticed="2026-06-01",
        latest_report="2026-06-03",
        rolling_window_count=3,
        new_since_last_alert=1,
        total_report_count=3,
        helpscout_links="",
        last_slack_alert_sent="2026-07-01T15:00:00+00:00",
        patch_date="",
        close_date="",
        owner="",
        engineering_link="",
        notes="",
        created_at="",
        updated_at="",
        issue_signature="finish_round_save_stuck",
        slack_channel_id="C123",
        slack_message_ts="123.456",
        slack_message_url="https://slack/message",
    )
    values.update(overrides)
    return IssueRecord(**values)


class RunDetectionTests(unittest.TestCase):
    def test_wastebasket_reaction_deletes_message_and_clears_slack_fields(self) -> None:
        delete_calls = []
        original_get = run_detection.get_message_reactions
        original_delete = run_detection.delete_issue_alert
        try:
            run_detection.get_message_reactions = lambda token, channel, ts: (SlackReaction("wastebasket", ("U123",), 1),)
            run_detection.delete_issue_alert = lambda token, channel, ts: delete_calls.append((token, channel, ts))

            synced = run_detection.sync_issue_status_from_reactions(issue(), settings(), "2026-07-02T15:00:00+00:00")
        finally:
            run_detection.get_message_reactions = original_get
            run_detection.delete_issue_alert = original_delete

        self.assertEqual(delete_calls, [("xoxb-token", "C123", "123.456")])
        self.assertEqual(synced.slack_channel_id, "")
        self.assertEqual(synced.slack_message_ts, "")
        self.assertEqual(synced.slack_message_deleted_by, "U123")

    def test_wastebasket_reaction_keeps_message_fields_when_delete_fails(self) -> None:
        original_get = run_detection.get_message_reactions
        original_delete = run_detection.delete_issue_alert
        try:
            run_detection.get_message_reactions = lambda token, channel, ts: (SlackReaction("wastebasket", ("U123",), 1),)

            def fail_delete(token: str, channel: str, ts: str) -> None:
                raise RuntimeError("nope")

            run_detection.delete_issue_alert = fail_delete

            with self.assertLogs("run_detection", level="WARNING"):
                synced = run_detection.sync_issue_status_from_reactions(issue(), settings(), "2026-07-02T15:00:00+00:00")
        finally:
            run_detection.get_message_reactions = original_get
            run_detection.delete_issue_alert = original_delete

        self.assertEqual(synced.slack_channel_id, "C123")
        self.assertEqual(synced.slack_message_ts, "123.456")
        self.assertEqual(synced.slack_message_deleted_by, "")


if __name__ == "__main__":
    unittest.main()
