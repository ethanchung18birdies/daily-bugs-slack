from __future__ import annotations

from datetime import date
import unittest

from issue_matching import heuristic_match_issues, heuristic_signature
from models import CleanedFeedback, IssueRecord, SourceReport


def report(content: str, index: int) -> SourceReport:
    return SourceReport(
        "June",
        index + 2,
        f"url-{index}",
        "Bug",
        content,
        date(2026, 6, 1),
        CleanedFeedback(content, None, "Android", None),
        "Android",
        content,
    )


class IssueMatchingTests(unittest.TestCase):
    def test_heuristic_signature_keeps_distinct_root_issues(self) -> None:
        self.assertNotEqual(
            heuristic_signature("Cannot finish round because loading spinner appears"),
            heuristic_signature("Round score is wrong after saving"),
        )

    def test_heuristic_match_links_existing_issue_by_signature(self) -> None:
        reports = [report("I cannot finish round because it is stuck loading", 0)]
        existing = [
            IssueRecord(
                "ISSUE-1",
                "Open",
                "Users cannot finish rounds",
                "Rounds",
                "",
                "",
                "",
                0,
                0,
                0,
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "finish_round_save_stuck",
            )
        ]

        clusters = heuristic_match_issues(reports, existing)

        self.assertEqual(clusters[0].issue_id, "ISSUE-1")
        self.assertEqual(clusters[0].match_type, "existing")


if __name__ == "__main__":
    unittest.main()
