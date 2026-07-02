from __future__ import annotations

from datetime import date
from pathlib import Path
import unittest

from alert_policy import decide_alert
from config import Settings
from models import CleanedFeedback, IssueRecord, SourceReport


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
        issue_summary="Users cannot finish round",
        feature_area="Rounds",
        platforms="",
        first_noticed="2026-06-01",
        latest_report="2026-06-03",
        rolling_window_count=3,
        new_since_last_alert=3,
        total_report_count=3,
        helpscout_links="",
        last_slack_alert_sent="",
        patch_date="",
        close_date="",
        owner="",
        engineering_link="",
        notes="",
        created_at="",
        updated_at="",
        issue_signature="finish_round_save_stuck",
        row_number=None,
    )
    values.update(overrides)
    return IssueRecord(**values)


def reports(count: int, submitted: date = date(2026, 6, 3)) -> list[SourceReport]:
    return [
        SourceReport(
            "June",
            index + 2,
            f"url-{index}",
            "Bug",
            "raw",
            submitted,
            CleanedFeedback("I cannot finish round", None, "Android", None),
            "Android",
            "I cannot finish round",
        )
        for index in range(count)
    ]


class AlertPolicyTests(unittest.TestCase):
    def test_new_issue_threshold(self) -> None:
        decision = decide_alert(issue=issue(), reports=reports(3), existing_issue=None, settings=settings())

        self.assertTrue(decision.should_alert)
        self.assertEqual(decision.alert_type, "new_issue")
        self.assertEqual(decision.slack_action, "post_new")

    def test_high_impact_threshold(self) -> None:
        decision = decide_alert(
            issue=issue(rolling_window_count=2, new_since_last_alert=2),
            reports=reports(2),
            existing_issue=None,
            settings=settings(),
        )

        self.assertTrue(decision.should_alert)

    def test_existing_update_threshold(self) -> None:
        existing = issue(last_slack_alert_sent="2026-06-01T15:00:00+00:00")
        decision = decide_alert(issue=issue(), reports=reports(3), existing_issue=existing, settings=settings())

        self.assertTrue(decision.should_alert)
        self.assertEqual(decision.alert_type, "existing_issue_update")

    def test_existing_issue_with_slack_message_updates_on_new_reports(self) -> None:
        existing = issue(
            last_slack_alert_sent="2026-06-01T15:00:00+00:00",
            slack_channel_id="C123",
            slack_message_ts="123.456",
        )
        decision = decide_alert(issue=issue(slack_channel_id="C123", slack_message_ts="123.456"), reports=reports(3), existing_issue=existing, settings=settings())

        self.assertTrue(decision.should_alert)
        self.assertEqual(decision.slack_action, "update_existing")

    def test_patched_threshold(self) -> None:
        decision = decide_alert(
            issue=issue(status="Patched", patch_date="2026-06-01"),
            reports=reports(2, date(2026, 6, 3)),
            existing_issue=issue(status="Patched", patch_date="2026-06-01"),
            settings=settings(),
        )

        self.assertTrue(decision.should_alert)
        self.assertEqual(decision.alert_type, "patched_regression")

    def test_dismissed_suppresses(self) -> None:
        decision = decide_alert(issue=issue(status="Dismissed"), reports=reports(5), existing_issue=None, settings=settings())

        self.assertFalse(decision.should_alert)

    def test_resolved_suppresses(self) -> None:
        decision = decide_alert(issue=issue(status="Resolved"), reports=reports(5), existing_issue=issue(status="Resolved"), settings=settings())

        self.assertFalse(decision.should_alert)
        self.assertEqual(decision.slack_action, "suppress_resolved")


if __name__ == "__main__":
    unittest.main()
