from __future__ import annotations

from datetime import date
import unittest

from models import AlertDecision, IssueRecord
from slack_alerts import build_issue_alert_payload, format_issue_alert


def issue(**overrides) -> IssueRecord:
    values = dict(
        issue_id="ISSUE-1",
        status="Monitoring",
        issue_summary="Users cannot finish or save rounds.",
        feature_area="Rounds",
        platforms="Android: 5",
        first_noticed="2026-06-01",
        latest_report="2026-06-03",
        rolling_window_count=7,
        new_since_last_alert=3,
        total_report_count=7,
        helpscout_links="https://secure.helpscout.net/conversation/1",
        last_slack_alert_sent="",
        patch_date="",
        close_date="",
        owner="",
        engineering_link="",
        notes="",
        created_at="",
        updated_at="",
        issue_signature="finish_round_save_stuck",
    )
    values.update(overrides)
    return IssueRecord(**values)


class SlackAlertsTests(unittest.TestCase):
    def test_format_issue_alert_is_concise(self) -> None:
        decision = AlertDecision(
            issue_id="ISSUE-1",
            alert_type="new_issue",
            should_alert=True,
            reason="threshold",
            rolling_window_count=7,
            new_since_last_alert=3,
            reports=(),
            issue_summary="Users cannot finish or save rounds.",
            platforms={"Android": 5, "iOS": 1, "Unknown": 1},
            first_noticed=date(2026, 6, 1),
            latest_report=date(2026, 6, 3),
            helpscout_links=("https://secure.helpscout.net/conversation/1",),
        )

        message = format_issue_alert(decision)

        self.assertIn("Possible Recurring Bug Detected", message)
        self.assertIn("Users cannot finish or save rounds.", message)
        self.assertIn("Android: 5", message)
        self.assertIn("June 1, 2026", message)
        self.assertNotIn("confidence", message.casefold())
        self.assertNotIn("reasoning", message.casefold())
        self.assertNotIn("customer quote", message.casefold())

    def test_build_issue_alert_payload_has_buttons(self) -> None:
        decision = AlertDecision(
            issue_id="ISSUE-1",
            alert_type="new_issue",
            should_alert=True,
            reason="threshold",
            rolling_window_count=7,
            new_since_last_alert=3,
            reports=(),
            issue_summary="Users cannot finish or save rounds.",
            platforms={"Android": 5},
            first_noticed=date(2026, 6, 1),
            latest_report=date(2026, 6, 3),
            helpscout_links=("https://secure.helpscout.net/conversation/1",),
            slack_action="post_new",
        )

        payload = build_issue_alert_payload(issue(), decision)

        self.assertEqual(payload["text"], "Monitoring: Users cannot finish or save rounds. (7 reports)")
        action_ids = [
            element["action_id"]
            for block in payload["blocks"]
            if block["type"] == "actions"
            for element in block["elements"]
        ]
        self.assertEqual(action_ids, ["acknowledge_issue", "resolve_issue"])

    def test_resolved_payload_removes_buttons(self) -> None:
        decision = AlertDecision(
            issue_id="ISSUE-1",
            alert_type="suppressed",
            should_alert=False,
            reason="resolved",
            rolling_window_count=7,
            new_since_last_alert=0,
            reports=(),
            issue_summary="Users cannot finish or save rounds.",
            platforms={"Android": 5},
            first_noticed=date(2026, 6, 1),
            latest_report=date(2026, 6, 3),
            helpscout_links=(),
            slack_action="suppress_resolved",
        )

        payload = build_issue_alert_payload(issue(status="Resolved"), decision)

        self.assertFalse(any(block["type"] == "actions" for block in payload["blocks"]))


if __name__ == "__main__":
    unittest.main()
