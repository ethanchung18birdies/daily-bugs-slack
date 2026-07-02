from __future__ import annotations

from datetime import date, datetime
import unittest
from zoneinfo import ZoneInfo

from report_parser import (
    clean_feedback,
    infer_platform_from_text,
    month_tabs_for_window,
    parse_source_rows,
    rolling_window,
    should_include_report,
)


PT = ZoneInfo("America/Los_Angeles")


class ReportParserTests(unittest.TestCase):
    def test_rolling_window_and_month_tabs_cross_boundary(self) -> None:
        start, end = rolling_window(date(2026, 6, 3), 7)

        self.assertEqual(start, date(2026, 5, 28))
        self.assertEqual(end, date(2026, 6, 3))
        self.assertEqual(month_tabs_for_window(start, end), ["May", "June"])

    def test_parse_source_rows_includes_bug_and_clear_broken_non_bug(self) -> None:
        values = [
            ["HelpScout Url", "Category", "Feedback", "Date Submitted", "Next Step", "Check CS Response"],
            ["1", "Bug", "App crashes when I finish round", "06/01/26", "", ""],
            ["2", "Feature Request", "The score will not save after the round", "06/02/26", "", ""],
            ["3", "Feature Request", "Please add a dark mode", "06/02/26", "", ""],
        ]

        reports = parse_source_rows("June", values, date(2026, 6, 1), date(2026, 6, 3))

        self.assertEqual([report.helpscout_url for report in reports], ["1", "2"])

    def test_clean_feedback_extracts_metadata(self) -> None:
        feedback = """Feedback from Dale Chu - ID: 69d8f641
Dale Chu
UserId: abc123
Club id: club-1
Nearest course name: Chesapeake
Is premiumUser: true
Device: SM-S928U1 36 16.29.0
Tags: suggestion.Or.Feedback
Feedback: I cannot save my score."""

        cleaned = clean_feedback(feedback)

        self.assertEqual(cleaned.content, "I cannot save my score.")
        self.assertEqual(cleaned.user_type, "Premium User")
        self.assertEqual(cleaned.device_type, "Android")
        self.assertEqual(cleaned.app_version, "16.29.0")
        self.assertEqual(cleaned.user_id, "abc123")
        self.assertEqual(cleaned.club_id, "club-1")
        self.assertEqual(cleaned.course_or_club_name, "Chesapeake")

    def test_platform_inference(self) -> None:
        self.assertEqual(infer_platform_from_text("iPhone iOS 26"), "iOS")
        self.assertEqual(infer_platform_from_text("Pixel 8 Pro"), "Android")
        self.assertEqual(infer_platform_from_text("Apple Watch score sync"), "Apple Watch")
        self.assertIsNone(infer_platform_from_text("browser"))

    def test_should_include_report(self) -> None:
        self.assertTrue(should_include_report("Bug", "anything"))
        self.assertTrue(should_include_report("Feature Request", "The app is stuck loading."))
        self.assertFalse(should_include_report("Feature Request", "Please add dark mode."))


if __name__ == "__main__":
    unittest.main()
