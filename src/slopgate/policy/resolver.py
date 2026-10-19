"""Action resolution engine for SlopGate.

Resolves multiple verdicts into a cohesive ActionPlan.
Enforces deterministic severity precedence: DENY > CONFIRM > GUIDE > PROCEED_SOFT > PROCEED.
Follows: architecture.md §6.5, PLAN_REVIEW.md §1.1.
"""

from __future__ import annotations

from slopgate.models import (
    ActionKind,
    ActionPlan,
    GateVerdict,
    PlannedToolCall,
)

# Severity precedence ranking (higher index = more restrictive / severe)
_SEVERITY_ORDER: dict[ActionKind, int] = {
    ActionKind.PROCEED: 1,
    ActionKind.PROCEED_SOFT: 2,
    ActionKind.GUIDE: 3,
    ActionKind.CONFIRM: 4,
    ActionKind.DENY: 5,
}


def resolve_verdicts(verdicts: list[GateVerdict]) -> ActionKind:
    """Resolve a list of GateVerdicts into a single overall ActionKind.

    Precedence: DENY > CONFIRM > GUIDE > PROCEED_SOFT > PROCEED.
    If verdicts is empty, defaults to ActionKind.CONFIRM for safety.
    """
    if not verdicts:
        return ActionKind.CONFIRM

    most_severe = ActionKind.PROCEED
    for v in verdicts:
        if _SEVERITY_ORDER[v.action] > _SEVERITY_ORDER[most_severe]:
            most_severe = v.action

    return most_severe


def build_action_plan(
    verdicts: list[GateVerdict],
    planned_steps: list[PlannedToolCall] | None = None,
    suggested_labels: list[str] | None = None,
    draft_comment: str | None = None,
) -> ActionPlan:
    """Build a comprehensive ActionPlan from evaluated verdicts and proposed actions."""
    overall = resolve_verdicts(verdicts)

    # Escalation triggers
    needs_reasoning = overall is ActionKind.GUIDE
    needs_draft = overall in (ActionKind.PROCEED_SOFT, ActionKind.GUIDE) or (
        draft_comment is not None and len(draft_comment) > 0
    )

    receipt_notes = [f"[{v.question_id}] {v.action.value.upper()}: {v.reason}" for v in verdicts]

    return ActionPlan(
        steps=planned_steps or [],
        overall=overall,
        needs_bedrock_draft=needs_draft,
        needs_bedrock_reasoning=needs_reasoning,
        receipt_notes=receipt_notes,
        suggested_labels=suggested_labels or [],
        draft_comment=draft_comment,
    )
