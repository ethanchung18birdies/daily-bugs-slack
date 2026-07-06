from __future__ import annotations

from datetime import date
import unittest

from models import AlertDecision, IssueRecord
import slack_alerts
from slack_alerts import (
    build_issue_alert_payload,
    delete_issue_alert,
    format_issue_alert,
    get_message_permalink,
    get_message_reactions,
    post_issue_alert,
)


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

    def test_build_issue_alert_payload_has_reaction_instructions(self) -> None:
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
        context_texts = [
            element["text"]
            for block in payload["blocks"]
            if block["type"] == "context"
            for element in block["elements"]
        ]
        self.assertEqual(
            context_texts,
            [
                "React with :eyes: to acknowledge, :white_check_mark: to resolve, "
                "or :wastebasket: to delete this Slack alert."
            ],
        )

    def test_resolved_payload_removes_reaction_instructions(self) -> None:
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

        self.assertFalse(any(block["type"] == "context" for block in payload["blocks"]))

    def test_get_message_reactions_parses_slack_response(self) -> None:
        original = slack_alerts._slack_api_get
        try:
            slack_alerts._slack_api_get = lambda token, method, params: {
                "ok": True,
                "message": {
                    "reactions": [
                        {"name": "eyes", "users": ["U1"], "count": 1},
                        {"name": "white_check_mark", "users": ["U2", "U3"], "count": 2},
                        {"name": "wastebasket", "users": ["U4"], "count": 1},
                    ]
                },
            }

            reactions = get_message_reactions("token", "C123", "123.456")
        finally:
            slack_alerts._slack_api_get = original

        self.assertEqual([reaction.name for reaction in reactions], ["eyes", "white_check_mark", "wastebasket"])
        self.assertEqual(reactions[1].users, ("U2", "U3"))

    def test_delete_issue_alert_calls_chat_delete(self) -> None:
        calls = []
        original = slack_alerts._slack_api_call
        try:
            slack_alerts._slack_api_call = lambda token, method, payload: calls.append((token, method, payload)) or {"ok": True}

            delete_issue_alert("token", "C123", "123.456")
        finally:
            slack_alerts._slack_api_call = original

        self.assertEqual(calls, [("token", "chat.delete", {"channel": "C123", "ts": "123.456"})])

    def test_get_message_permalink_uses_get(self) -> None:
        calls = []
        original = slack_alerts._slack_api_get
        try:
            slack_alerts._slack_api_get = lambda token, method, params: calls.append((token, method, params)) or {"permalink": "https://slack/permalink"}

            permalink = get_message_permalink("token", "C123", "123.456")
        finally:
            slack_alerts._slack_api_get = original

        self.assertEqual(permalink, "https://slack/permalink")
        self.assertEqual(calls, [("token", "chat.getPermalink", {"channel": "C123", "message_ts": "123.456"})])

    def test_post_issue_alert_keeps_ts_when_permalink_fails(self) -> None:
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
        original_call = slack_alerts._slack_api_call
        original_get = slack_alerts._slack_api_get
        try:
            slack_alerts._slack_api_call = lambda token, method, payload: {"ok": True, "channel": "C123", "ts": "123.456"}

            def fail_get(token: str, method: str, params: dict) -> dict:
                raise RuntimeError("invalid_arguments")

            slack_alerts._slack_api_get = fail_get

            with self.assertLogs("slack_alerts", level="WARNING"):
                result = post_issue_alert("token", "C123", issue(), decision)
        finally:
            slack_alerts._slack_api_call = original_call
            slack_alerts._slack_api_get = original_get

        self.assertEqual(result.channel_id, "C123")
        self.assertEqual(result.message_ts, "123.456")
        self.assertEqual(result.message_url, "")


if __name__ == "__main__":
    unittest.main()
