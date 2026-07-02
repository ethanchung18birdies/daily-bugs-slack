from __future__ import annotations

from dataclasses import dataclass

from models import IssueRecord


@dataclass(frozen=True)
class IssueActionResult:
    issue: IssueRecord
    previous_status: str
    new_status: str
    action: str


def apply_issue_action(
    issue: IssueRecord,
    *,
    action: str,
    actor: str,
    acted_at: str,
) -> IssueActionResult:
    if action == "acknowledge_issue":
        return _replace_issue(
            issue,
            action=action,
            actor=actor,
            acted_at=acted_at,
            values={
                "status": "Acknowledged",
                "acknowledged_at": acted_at,
                "acknowledged_by": actor,
            },
        )
    if action == "resolve_issue":
        return _replace_issue(
            issue,
            action=action,
            actor=actor,
            acted_at=acted_at,
            values={
                "status": "Resolved",
                "resolved_at": acted_at,
                "resolved_by": actor,
                "close_date": acted_at.split("T", 1)[0],
            },
        )
    raise ValueError(f"Unsupported issue action: {action}")


def _replace_issue(
    issue: IssueRecord,
    *,
    action: str,
    actor: str,
    acted_at: str,
    values: dict[str, str],
) -> IssueActionResult:
    del actor, acted_at
    previous_status = issue.status
    next_issue = IssueRecord(**{**issue.__dict__, **values})
    return IssueActionResult(
        issue=next_issue,
        previous_status=previous_status,
        new_status=next_issue.status,
        action=action,
    )
