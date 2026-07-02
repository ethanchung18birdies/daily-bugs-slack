from __future__ import annotations

from dataclasses import dataclass

from models import IssueRecord
from slack_alerts import SlackReaction


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


def apply_reaction_status(
    issue: IssueRecord,
    *,
    reactions: tuple[SlackReaction, ...],
    acted_at: str,
) -> IssueActionResult | None:
    reaction_users = {reaction.name: reaction.users for reaction in reactions}
    if reaction_users.get("white_check_mark") and issue.status != "Resolved":
        return apply_issue_action(
            issue,
            action="resolve_issue",
            actor=_format_reaction_actor(reaction_users["white_check_mark"]),
            acted_at=acted_at,
        )
    if reaction_users.get("eyes") and issue.status == "Monitoring":
        return apply_issue_action(
            issue,
            action="acknowledge_issue",
            actor=_format_reaction_actor(reaction_users["eyes"]),
            acted_at=acted_at,
        )
    return None


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


def _format_reaction_actor(users: tuple[str, ...]) -> str:
    if not users:
        return ""
    if len(users) == 1:
        return users[0]
    return ", ".join(users)
