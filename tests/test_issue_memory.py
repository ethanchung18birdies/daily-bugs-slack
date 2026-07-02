from __future__ import annotations

from datetime import date
import unittest

from issue_memory import build_updated_issue, find_existing_issue, issue_from_row, issue_to_row
from models import CleanedFeedback, IssueCluster, IssueRecord, SourceReport


def report(url: str, submitted: date, platform: str = "Android") -> SourceReport:
    return SourceReport(
        source_tab="June",
        row_number=2,
        helpscout_url=url,
        category="Bug",
        feedback_raw="raw",
        date_submitted=submitted,
        cleaned_feedback=CleanedFeedback(content="Cannot finish round", user_type=None, device_type=platform, app_version=None),
        platform=platform,
        report_summary="Cannot finish round",
    )


class IssueMemoryTests(unittest.TestCase):
    def test_issue_row_round_trip(self) -> None:
        row = {
            "issue_id": "ISSUE-1",
            "status": "Open",
            "issue_summary": "Users cannot finish rounds",
            "feature_area": "Rounds",
            "rolling_window_count": "3",
            "new_since_last_alert": "2",
            "total_report_count": "5",
            "issue_signature": "finish_round_save_stuck",
            "slack_channel_id": "C123",
            "slack_message_ts": "123.456",
            "acknowledged_by": "Ethan",
        }

        issue = issue_from_row(row, row_number=7)

        self.assertEqual(issue.row_number, 7)
        self.assertEqual(issue.status, "Open")
        self.assertEqual(issue.rolling_window_count, 3)
        self.assertEqual(issue.slack_channel_id, "C123")
        self.assertEqual(issue.slack_message_ts, "123.456")
        self.assertEqual(issue.acknowledged_by, "Ethan")
        self.assertEqual(issue_to_row(issue)[0], "ISSUE-1")
        self.assertEqual(len(issue_to_row(issue)), 28)

    def test_build_updated_issue_creates_new_issue(self) -> None:
        cluster = IssueCluster(
            issue_id=None,
            issue_summary="Users cannot finish or save rounds",
            feature_area="Rounds / Scoring",
            issue_signature="finish_round_save_stuck",
            report_indices=(0, 1),
            match_type="new",
            confidence=0.9,
        )

        issue = build_updated_issue(
            cluster,
            [report("a", date(2026, 6, 1)), report("b", date(2026, 6, 3), "iOS")],
            None,
            "2026-06-04T15:00:00+00:00",
        )

        self.assertTrue(issue.issue_id.startswith("ISSUE-20260601-"))
        self.assertEqual(issue.status, "Monitoring")
        self.assertEqual(issue.first_noticed, "2026-06-01")
        self.assertEqual(issue.latest_report, "2026-06-03")
        self.assertEqual(issue.rolling_window_count, 2)
        self.assertIn("Android: 1", issue.platforms)
        self.assertIn("iOS: 1", issue.platforms)

    def test_find_existing_issue_can_match_suppressed_statuses(self) -> None:
        cluster = IssueCluster("ISSUE-1", "Summary", "Area", "sig", (0,), "existing", 0.9)
        issues = [
            IssueRecord("ISSUE-1", "Closed", "", "", "", "", "", 0, 0, 0, "", "", "", "", "", "", "", "", "", "sig"),
            IssueRecord("ISSUE-2", "Open", "", "", "", "", "", 0, 0, 0, "", "", "", "", "", "", "", "", "", "sig"),
        ]

        self.assertEqual(find_existing_issue(cluster, issues).issue_id, "ISSUE-1")


if __name__ == "__main__":
    unittest.main()
