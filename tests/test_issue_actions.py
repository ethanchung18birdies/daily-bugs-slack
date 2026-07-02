from __future__ import annotations

import unittest

from issue_actions import apply_issue_action
from models import IssueRecord


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


class IssueActionsTests(unittest.TestCase):
    def test_acknowledge_issue(self) -> None:
        result = apply_issue_action(
            issue(),
            action="acknowledge_issue",
            actor="Ethan",
            acted_at="2026-07-02T15:00:00+00:00",
        )

        self.assertEqual(result.previous_status, "Monitoring")
        self.assertEqual(result.new_status, "Acknowledged")
        self.assertEqual(result.issue.acknowledged_by, "Ethan")
        self.assertEqual(result.issue.acknowledged_at, "2026-07-02T15:00:00+00:00")

    def test_resolve_issue(self) -> None:
        result = apply_issue_action(
            issue(status="Acknowledged"),
            action="resolve_issue",
            actor="Ethan",
            acted_at="2026-07-02T15:00:00+00:00",
        )

        self.assertEqual(result.previous_status, "Acknowledged")
        self.assertEqual(result.new_status, "Resolved")
        self.assertEqual(result.issue.resolved_by, "Ethan")
        self.assertEqual(result.issue.close_date, "2026-07-02")


if __name__ == "__main__":
    unittest.main()
