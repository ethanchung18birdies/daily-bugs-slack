from __future__ import annotations

from datetime import date
import unittest

from models import AlertDecision
from slack_alerts import format_issue_alert


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


if __name__ == "__main__":
    unittest.main()
