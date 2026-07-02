from __future__ import annotations

import unittest

from issue_actions import apply_issue_action, apply_reaction_status
from models import IssueRecord
from slack_alerts import SlackReaction


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

    def test_eyes_reaction_acknowledges_monitoring_issue(self) -> None:
        result = apply_reaction_status(
            issue(),
            reactions=(SlackReaction("eyes", ("U123",), 1),),
            acted_at="2026-07-02T15:00:00+00:00",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.issue.status, "Acknowledged")
        self.assertEqual(result.issue.acknowledged_by, "U123")

    def test_green_check_reaction_resolves_and_wins_over_eyes(self) -> None:
        result = apply_reaction_status(
            issue(),
            reactions=(
                SlackReaction("eyes", ("U123",), 1),
                SlackReaction("white_check_mark", ("U456",), 1),
            ),
            acted_at="2026-07-02T15:00:00+00:00",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.issue.status, "Resolved")
        self.assertEqual(result.issue.resolved_by, "U456")

    def test_eyes_reaction_does_not_downgrade_acknowledged_issue(self) -> None:
        result = apply_reaction_status(
            issue(status="Acknowledged"),
            reactions=(SlackReaction("eyes", ("U123",), 1),),
            acted_at="2026-07-02T15:00:00+00:00",
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
