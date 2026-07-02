from __future__ import annotations

from collections import defaultdict
import json
import logging
import re

from config import Settings
from models import IssueCluster, IssueRecord, SourceReport
from report_parser import normalize_signature_text


LOGGER = logging.getLogger("issue_matching")


def match_issues(
    reports: list[SourceReport],
    existing_issues: list[IssueRecord],
    settings: Settings,
) -> list[IssueCluster]:
    if not reports:
        return []
    try:
        return _openai_match_issues(reports, existing_issues, settings)
    except Exception as exc:  # pragma: no cover - exercised through fallback tests with direct call
        LOGGER.warning("OpenAI matching failed; falling back to heuristic matching: %s", exc)
        return heuristic_match_issues(reports, existing_issues)


def _openai_match_issues(
    reports: list[SourceReport],
    existing_issues: list[IssueRecord],
    settings: Settings,
) -> list[IssueCluster]:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    payload = {
        "reports": [
            {
                "index": index,
                "date": report.date_submitted.isoformat(),
                "platform": report.platform,
                "summary": report.report_summary,
                "feedback": report.cleaned_feedback.content[:1200],
            }
            for index, report in enumerate(reports)
        ],
        "existing_issues": [
            {
                "issue_id": issue.issue_id,
                "status": issue.status,
                "issue_summary": issue.issue_summary,
                "feature_area": issue.feature_area,
                "issue_signature": issue.issue_signature,
            }
            for issue in existing_issues
            if issue.status not in {"Closed", "Dismissed"}
        ],
    }
    response = client.chat.completions.create(
        model=settings.openai_model,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You group customer support reports into recurring product issues. "
                    "Prefer fewer, higher-confidence clusters. Do not group by broad feature area alone. "
                    "Different root behaviors must be separate issues. Return only JSON."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Given reports and existing issues, return JSON with key 'clusters'. Each cluster must have "
                    "issue_id (existing issue id or null), issue_summary, feature_area, issue_signature, "
                    "report_indices, match_type ('existing' or 'new'), and confidence 0-1.\n\n"
                    + json.dumps(payload, ensure_ascii=False)
                ),
            },
        ],
    )
    content = response.choices[0].message.content or "{}"
    parsed = json.loads(content)
    return _clusters_from_json(parsed, len(reports))


def heuristic_match_issues(reports: list[SourceReport], existing_issues: list[IssueRecord]) -> list[IssueCluster]:
    groups: dict[str, list[int]] = defaultdict(list)
    for index, report in enumerate(reports):
        signature = heuristic_signature(report.cleaned_feedback.content)
        groups[signature].append(index)

    clusters: list[IssueCluster] = []
    for signature, indices in groups.items():
        matching_issue = next(
            (issue for issue in existing_issues if issue.issue_signature == signature and issue.status not in {"Closed", "Dismissed"}),
            None,
        )
        summary = summarize_cluster([reports[index] for index in indices])
        clusters.append(
            IssueCluster(
                issue_id=matching_issue.issue_id if matching_issue else None,
                issue_summary=matching_issue.issue_summary if matching_issue else summary,
                feature_area=infer_feature_area(signature),
                issue_signature=signature,
                report_indices=tuple(indices),
                match_type="existing" if matching_issue else "new",
                confidence=0.62,
            )
        )
    return clusters


def heuristic_signature(content: str) -> str:
    normalized = normalize_signature_text(content)
    rules = (
        ("finish_round_save_stuck", r"\b(finish|save|close|end).{0,40}\b(round|score)|\b(round|score).{0,40}\b(finish|save|close|end)|stuck.{0,40}round"),
        ("score_sync_loss", r"\b(score|scores).{0,40}\b(sync|submit|lost|missing|save)"),
        ("login_access", r"\b(login|log in|sign in|account access)"),
        ("subscription_payment_access", r"\b(subscription|payment|premium|billing|charge)"),
        ("apple_watch_sync", r"\b(apple watch|watch).{0,50}\b(sync|score|scores)"),
        ("gps_distance_wrong", r"\b(gps|distance|yardage).{0,40}\b(wrong|incorrect|off|inaccurate)"),
        ("league_leaderboard", r"\b(league|leaderboard).{0,40}\b(point|score|standing|rank)"),
        ("app_crash", r"\b(crash|crashes|crashing)"),
    )
    for signature, pattern in rules:
        if re.search(pattern, normalized):
            return signature
    tokens = normalized.split()[:8]
    return "_".join(tokens) or "unknown_issue"


def summarize_cluster(reports: list[SourceReport]) -> str:
    if not reports:
        return "Recurring customer-reported issue"
    summary = reports[0].report_summary.rstrip(".")
    return summary or "Recurring customer-reported issue"


def infer_feature_area(signature: str) -> str:
    if "round" in signature or "score" in signature:
        return "Rounds / Scoring"
    if "watch" in signature:
        return "Apple Watch"
    if "gps" in signature:
        return "GPS"
    if "subscription" in signature or "payment" in signature:
        return "Subscription / Billing"
    if "league" in signature:
        return "Leagues"
    if "login" in signature:
        return "Login / Account"
    return "Other"


def _clusters_from_json(parsed: dict, report_count: int) -> list[IssueCluster]:
    clusters: list[IssueCluster] = []
    for raw in parsed.get("clusters", []):
        indices = tuple(
            sorted(
                {
                    int(index)
                    for index in raw.get("report_indices", [])
                    if isinstance(index, int) or str(index).isdigit()
                }
            )
        )
        indices = tuple(index for index in indices if 0 <= index < report_count)
        if not indices:
            continue
        summary = str(raw.get("issue_summary", "")).strip() or "Recurring customer-reported issue"
        signature = str(raw.get("issue_signature", "")).strip() or heuristic_signature(summary)
        clusters.append(
            IssueCluster(
                issue_id=(str(raw.get("issue_id")).strip() if raw.get("issue_id") else None),
                issue_summary=summary,
                feature_area=str(raw.get("feature_area", "")).strip() or infer_feature_area(signature),
                issue_signature=signature,
                report_indices=indices,
                match_type=str(raw.get("match_type", "new")).strip() or "new",
                confidence=float(raw.get("confidence", 0) or 0),
            )
        )
    return clusters
