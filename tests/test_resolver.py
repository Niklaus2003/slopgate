"""Unit tests for ActionResolver and severity ordering."""

from slopgate.models import ActionKind, Band, GateVerdict
from slopgate.policy.resolver import build_action_plan, resolve_verdicts


def test_severity_order_precedence():
    # DENY beats everything
    v_deny = GateVerdict(question_id="Q1", band=Band.HIGH, action=ActionKind.DENY, reason="denied")
    v_confirm = GateVerdict(question_id="Q2", band=Band.MEDIUM, action=ActionKind.CONFIRM, reason="confirm")
    v_guide = GateVerdict(question_id="Q3", band=Band.LOW, action=ActionKind.GUIDE, reason="guide")
    v_proceed_soft = GateVerdict(question_id="Q4", band=Band.HIGH, action=ActionKind.PROCEED_SOFT, reason="soft")
    v_proceed = GateVerdict(question_id="Q5", band=Band.HIGH, action=ActionKind.PROCEED, reason="proceed")

    assert resolve_verdicts([v_proceed, v_proceed_soft, v_guide, v_confirm, v_deny]) == ActionKind.DENY
    assert resolve_verdicts([v_proceed, v_proceed_soft, v_guide, v_confirm]) == ActionKind.CONFIRM
    assert resolve_verdicts([v_proceed, v_proceed_soft, v_guide]) == ActionKind.GUIDE
    assert resolve_verdicts([v_proceed, v_proceed_soft]) == ActionKind.PROCEED_SOFT
    assert resolve_verdicts([v_proceed]) == ActionKind.PROCEED


def test_empty_verdicts_defaults_to_confirm():
    assert resolve_verdicts([]) == ActionKind.CONFIRM


def test_build_action_plan():
    v_guide = GateVerdict(question_id="Q1", band=Band.LOW, action=ActionKind.GUIDE, reason="Unclear issue")
    plan = build_action_plan(verdicts=[v_guide])

    assert plan.overall == ActionKind.GUIDE
    assert plan.needs_bedrock_reasoning is True
    assert plan.needs_bedrock_draft is True
    assert len(plan.receipt_notes) == 1
    assert "UNCLEAR ISSUE" in plan.receipt_notes[0].upper()
