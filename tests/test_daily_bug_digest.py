from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from daily_bug_digest import (  # noqa: E402
    FeedbackRow,
    clean_feedback,
    filter_daily_bugs,
    format_helpscout_reference,
    format_metadata,
    format_slack_message,
    month_tab_name,
    parse_sheet_date,
    previous_report_date,
    rows_from_values,
)


PT = ZoneInfo("America/Los_Angeles")


def row(
    *,
    category: str = "Bug",
    date_submitted: str = "05/28/26",
    helpscout_url: str = "https://secure.helpscout.net/conversation/3331778894",
    feedback: str = "Full bug feedback",
    next_step: str = "",
) -> FeedbackRow:
    return FeedbackRow(
        tab_name="May",
        row_number=2,
        helpscout_url=helpscout_url,
        category=category,
        feedback=feedback,
        date_submitted_raw=date_submitted,
        next_step=next_step,
        check_cs_response="",
    )


class DailyBugDigestTests(unittest.TestCase):
    def test_previous_report_date_uses_yesterday_pt(self) -> None:
        self.assertEqual(
            previous_report_date(datetime(2026, 5, 29, 8, tzinfo=PT)),
            date(2026, 5, 28),
        )

    def test_previous_report_date_handles_month_boundary(self) -> None:
        report_date = previous_report_date(datetime(2026, 6, 1, 8, tzinfo=PT))

        self.assertEqual(report_date, date(2026, 5, 31))
        self.assertEqual(month_tab_name(report_date), "May")

    def test_parse_sheet_date_accepts_common_formats(self) -> None:
        cases = {
            "05/28/26": date(2026, 5, 28),
            "5/28/2026": date(2026, 5, 28),
            "2026-05-28": date(2026, 5, 28),
            "2026-05-28 08:39": date(2026, 5, 28),
            "2026-05-28T17:30:00Z": date(2026, 5, 28),
        }

        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(parse_sheet_date(value), expected)

    def test_parse_sheet_date_converts_aware_timestamp_to_pt_date(self) -> None:
        self.assertEqual(parse_sheet_date("2026-05-29T06:30:00Z"), date(2026, 5, 28))

    def test_parse_sheet_date_returns_none_for_invalid_values(self) -> None:
        self.assertIsNone(parse_sheet_date(""))
        self.assertIsNone(parse_sheet_date("not a date"))

    def test_rows_from_values_maps_expected_columns(self) -> None:
        rows = rows_from_values(
            "May",
            [
                [
                    "HelpScout Url",
                    "Category",
                    "Feedback",
                    "Date Submitted",
                    "Next Step",
                    "Check CS Response",
                ],
                ["123", "Bug", "App freezes", "05/28/26", "Investigate", ""],
            ],
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].helpscout_url, "123")
        self.assertEqual(rows[0].feedback, "App freezes")
        self.assertEqual(rows[0].next_step, "Investigate")

    def test_filter_daily_bugs_matches_bug_category_and_report_date(self) -> None:
        rows = [
            row(date_submitted="05/28/26"),
            row(category="Feature Request", date_submitted="05/28/26"),
            row(date_submitted="05/27/26"),
            row(date_submitted="not a date"),
        ]

        bugs = filter_daily_bugs(rows, date(2026, 5, 28))

        self.assertEqual(bugs, [rows[0]])

    def test_format_helpscout_reference_formats_urls_as_slack_links(self) -> None:
        value = "https://secure.helpscout.net/conversation/3331778894"

        self.assertEqual(format_helpscout_reference(value), f"<{value}|{value}>")

    def test_format_helpscout_reference_keeps_id_only_values(self) -> None:
        self.assertEqual(format_helpscout_reference("3331778894"), "3331778894")

    def test_format_slack_message_zero_bugs(self) -> None:
        self.assertEqual(
            format_slack_message([], date(2026, 5, 28)),
            "Daily CS Product Bugs: 0 from May 28",
        )

    def test_format_slack_message_keeps_full_feedback_and_next_step(self) -> None:
        feedback = "Line one of the report.\nLine two has more detail and should not be truncated."
        message = format_slack_message(
            [row(feedback=feedback, next_step="Try to reproduce on iOS.")],
            date(2026, 5, 28),
        )

        self.assertIn("*Daily CS Product Bugs: 1 from May 28*", message)
        self.assertIn(feedback, message)
        self.assertIn("*Next Step:* Try to reproduce on iOS.", message)

    def test_clean_feedback_extracts_premium_android_metadata(self) -> None:
        feedback = """Feedback from Dale Chu - ID: 69d8f641-5b6f-11f1-aa26-02d9778a0d31
Dale Chu (dalechu1@yahoo.com)
Is premiumUser: true
Device: SM-S928U1 36 16.29.0
Tags: suggestion.Or.Feedback
Feedback: I have a lot of screenshots for the same error this time."""

        cleaned = clean_feedback(feedback)

        self.assertEqual(cleaned.user_type, "Premium User")
        self.assertEqual(cleaned.device_type, "Android")
        self.assertEqual(cleaned.app_version, "16.29.0")
        self.assertEqual(cleaned.content, "I have a lot of screenshots for the same error this time.")
        self.assertEqual(format_metadata(cleaned), "Premium User | Android | 16.29.0")

    def test_clean_feedback_extracts_standard_ios_metadata(self) -> None:
        feedback = """Feedback from Tyler Cutchall - ID: 7a12b051-5a98-11f1-a494-02d9778a0d31
Tyler Cutchall (packerfan082002@yahoo.com)
Is premiumUser: false
Device: iPhone 17 Pro Max(iPhone18,2) iOS 26.5 16.29.1
Tags: suggestion.Or.Feedback
Feedback: Fix this app. Comments have not been working for months."""

        cleaned = clean_feedback(feedback)

        self.assertEqual(cleaned.user_type, "Standard User")
        self.assertEqual(cleaned.device_type, "iOS")
        self.assertEqual(cleaned.app_version, "16.29.1")
        self.assertEqual(cleaned.content, "Fix this app. Comments have not been working for months.")

    def test_clean_feedback_uses_final_feedback_marker(self) -> None:
        feedback = """Feedback from Someone - ID: abc
Device: Pixel 8 Pro 36 16.29.0
Notes before actual message mention Feedback: old duplicated preamble.
Feedback: Actual customer message only."""

        cleaned = clean_feedback(feedback)

        self.assertEqual(cleaned.content, "Actual customer message only.")
        self.assertNotIn("old duplicated preamble", cleaned.content)

    def test_unstructured_feedback_is_preserved_without_metadata(self) -> None:
        feedback = """Incorrect handicap Hi, I am a 26 handicap and just entered a +10 9 hole score card.
This must be a mistake. How can I fix this? Thanks
See attached pictures
Sent from Outlook for iOS"""

        cleaned = clean_feedback(feedback)
        message = format_slack_message([row(feedback=feedback)], date(2026, 5, 28))

        self.assertEqual(cleaned.content, feedback)
        self.assertIsNone(cleaned.user_type)
        self.assertIsNone(cleaned.device_type)
        self.assertIsNone(cleaned.app_version)
        self.assertNotIn("*Metadata:*", message)
        self.assertIn(feedback, message)

    def test_format_slack_message_renders_structured_metadata_and_clean_content(self) -> None:
        feedback = """Feedback from Jim Blalock - ID: 0df87021-5ab2-11f1-9b8f-026cea355d3f
Jim Blalock (hb.blalock@gmail.com)
Is premiumUser: true
Device: Pixel 10 Pro XL 36 16.29.0
Tags: suggestion.Or.Feedback
Feedback: I have an open round that I cannot finish or delete."""

        message = format_slack_message([row(feedback=feedback)], date(2026, 5, 28))

        self.assertIn("*Metadata:* Premium User | Android | 16.29.0", message)
        self.assertIn("*Feedback:*\nI have an open round that I cannot finish or delete.", message)
        self.assertNotIn("Jim Blalock (hb.blalock@gmail.com)", message)

    def test_format_slack_message_adds_separator_between_tickets(self) -> None:
        message = format_slack_message(
            [
                row(feedback="First bug"),
                row(feedback="Second bug"),
            ],
            date(2026, 5, 28),
        )

        self.assertIn("\n===\n\n*2. HelpScout:*", message)
        self.assertEqual(message.count("==="), 1)

    def test_clean_beacon_feedback_extracts_android_device_and_final_message(self) -> None:
        feedback = """"Stuck in round I'm currently stuck in a round. Technical Information
IP Address
35.148.64.23
Operating System
Android OS Unknown
Browser/Version
Android 4.0
Device
Mobile Phone
Authentication Mode
Basic
Beacon History
Viewed Search results for Stuck in round | 18Birdies Knowledge Base / https://help.18birdies.com/search?query=Stuck+in+round
Beacon opened on Search results for Stuck in round | 18Birdies Knowledge Base / https://help.18birdies.com/search?query=Stuck+in+round
I'm currently stuck in a round. Unable to delete, finish the round, or edit scores or return to GPS. Unable to start a new round. Have rebooted the app several times and it has been 5 hours since completed."
"""

        cleaned = clean_feedback(feedback)

        self.assertEqual(cleaned.device_type, "Android")
        self.assertIsNone(cleaned.user_type)
        self.assertIsNone(cleaned.app_version)
        self.assertEqual(
            cleaned.content,
            "I'm currently stuck in a round. Unable to delete, finish the round, or edit scores or return to GPS. Unable to start a new round. Have rebooted the app several times and it has been 5 hours since completed.",
        )

    def test_clean_beacon_feedback_extracts_ios_device(self) -> None:
        feedback = """Technical Information
Operating System
iOS 26.5
Device
Mobile Phone
Beacon History
Beacon opened on 18Birdies Knowledge Base / https://help.18birdies.com
The app crashes when I finish the round."""

        cleaned = clean_feedback(feedback)

        self.assertEqual(cleaned.device_type, "iOS")
        self.assertEqual(cleaned.content, "The app crashes when I finish the round.")

    def test_clean_beacon_feedback_falls_back_to_text_before_technical_info(self) -> None:
        feedback = """"App Issues Good day. The app loops when I save and exit.
Thank you,
Dan Technical Information
Operating System
Android OS Unknown
Beacon History
Beacon opened on 18Birdies Knowledge Base / https://help.18birdies.com
"
"""

        cleaned = clean_feedback(feedback)

        self.assertEqual(cleaned.device_type, "Android")
        self.assertEqual(
            cleaned.content,
            "App Issues Good day. The app loops when I save and exit.\nThank you,\nDan",
        )

    def test_format_slack_message_renders_beacon_metadata(self) -> None:
        feedback = """Technical Information
Operating System
Android OS Unknown
Beacon History
Beacon opened on 18Birdies Knowledge Base / https://help.18birdies.com
The round will not close."""

        message = format_slack_message([row(feedback=feedback)], date(2026, 5, 28))

        self.assertIn("*Metadata:* Android", message)
        self.assertIn("*Feedback:*\nThe round will not close.", message)
        self.assertNotIn("Technical Information", message)


if __name__ == "__main__":
    unittest.main()
