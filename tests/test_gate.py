"""Unit tests for ConfidenceGate policy evaluation and safety invariants."""

from slopgate.config import (
    PolicyConfig,
    RoutingEntryConfig,
    ToolGateEntryConfig,
)
from slopgate.models import ActionKind, Band, DeciderResult
from slopgate.policy.gate import ConfidenceGate


def create_test_policy() -> PolicyConfig:
    policy = PolicyConfig()
    policy.tools_gated = {
        "apply_label": ToolGateEntryConfig(requires=["Q1"]),
        "post_comment": ToolGateEntryConfig(requires=["Q1"]),
        "close_item": ToolGateEntryConfig(always="confirm"),
    }
    policy.routing = {
        "real_bug_report": RoutingEntryConfig(high="proceed", medium="confirm", low="guide"),
        "low_effort": RoutingEntryConfig(high="proceed_soft", medium="confirm", low="guide"),
        "security_report": RoutingEntryConfig(high="confirm", medium="confirm", low="confirm"),
        "support_question": RoutingEntryConfig(high="proceed", medium="confirm", low="guide"),
    }
    return policy


def test_close_item_never_proceeds():
    """CRITICAL SAFETY INVARIANT 1:

    Even with 100% certainty (confidence=1.0) that an item is 'low_effort',
    'close_item' must NEVER result in ActionKind.PROCEED or PROCEED_SOFT.
    """
    gate = ConfidenceGate()
    policy = create_test_policy()

    # Even if policy somehow misconfigured close_item or decider was 100% sure
    decisions = [
        DeciderResult(
            question_id="Q1",
            qtype="choice",
            answer="low_effort",
            probs={"low_effort": 1.0, "real_bug_report": 0.0},
            confidence=1.0,
        )
    ]

    verdict = gate.evaluate(tool_name="close_item", decisions=decisions, policy=policy)
    assert verdict.action == ActionKind.CONFIRM
    assert verdict.action != ActionKind.PROCEED
    assert verdict.action != ActionKind.PROCEED_SOFT
    assert "INVARIANT 1" in verdict.reason


def test_security_report_is_at_least_confirm():
    """Security reports must always require maintainer confirmation."""
    gate = ConfidenceGate()
    policy = create_test_policy()

    decisions = [
        DeciderResult(
            question_id="Q1",
            qtype="choice",
            answer="security_report",
            probs={"security_report": 0.99, "real_bug_report": 0.01},
            confidence=0.98,
        )
    ]

    verdict = gate.evaluate(tool_name="apply_label", decisions=decisions, policy=policy)
    assert verdict.action == ActionKind.CONFIRM
    assert verdict.action != ActionKind.PROCEED
    assert "Security reports require maintainer review" in verdict.reason


def test_unlisted_tool_defaults_to_confirm():
    """Tools not explicitly declared in policy must default to CONFIRM."""
    gate = ConfidenceGate()
    policy = create_test_policy()

    decisions = [
        DeciderResult(
            question_id="Q1",
            qtype="choice",
            answer="real_bug_report",
            probs={"real_bug_report": 0.95, "low_effort": 0.05},
            confidence=0.90,
        )
    ]

    verdict = gate.evaluate(tool_name="arbitrary_unlisted_tool", decisions=decisions, policy=policy)
    assert verdict.action == ActionKind.CONFIRM
    assert "not declared in policy.tools_gated" in verdict.reason


def test_real_bug_report_with_reproduction_proceeds():
    gate = ConfidenceGate()
    policy = create_test_policy()

    decisions = [
        DeciderResult(
            question_id="Q1",
            qtype="choice",
            answer="real_bug_report",
            probs={"real_bug_report": 0.95, "low_effort": 0.05},
            confidence=0.90,
        ),
        DeciderResult(
            question_id="N1",
            qtype="noul",
            answer=True,
            probs={"true": 0.95, "false": 0.05},
        ),
    ]

    verdict = gate.evaluate(tool_name="apply_label", decisions=decisions, policy=policy)
    assert verdict.action == ActionKind.PROCEED
    assert verdict.band == Band.HIGH


def test_real_bug_report_without_reproduction_is_proceed_soft():
    gate = ConfidenceGate()
    policy = create_test_policy()

    decisions = [
        DeciderResult(
            question_id="Q1",
            qtype="choice",
            answer="real_bug_report",
            probs={"real_bug_report": 0.95, "low_effort": 0.05},
            confidence=0.90,
        ),
        DeciderResult(
            question_id="N1",
            qtype="noul",
            answer=False,
            probs={"true": 0.05, "false": 0.95},
        ),
    ]

    verdict = gate.evaluate(tool_name="apply_label", decisions=decisions, policy=policy)
    assert verdict.action == ActionKind.PROCEED_SOFT
    assert verdict.is_soft is True


def test_low_effort_high_confidence_is_proceed_soft():
    gate = ConfidenceGate()
    policy = create_test_policy()

    decisions = [
        DeciderResult(
            question_id="Q1",
            qtype="choice",
            answer="low_effort",
            probs={"low_effort": 0.92, "real_bug_report": 0.08},
            confidence=0.88,
        )
    ]

    verdict = gate.evaluate(tool_name="apply_label", decisions=decisions, policy=policy)
    assert verdict.action == ActionKind.PROCEED_SOFT
    assert verdict.is_soft is True


def test_medium_confidence_routes_to_confirm():
    gate = ConfidenceGate()
    policy = create_test_policy()

    decisions = [
        DeciderResult(
            question_id="Q1",
            qtype="choice",
            answer="real_bug_report",
            probs={"real_bug_report": 0.65, "low_effort": 0.35},
            confidence=0.60,
        )
    ]

    verdict = gate.evaluate(tool_name="apply_label", decisions=decisions, policy=policy)
    assert verdict.action == ActionKind.CONFIRM
    assert verdict.band == Band.MEDIUM


def test_low_confidence_routes_to_guide():
    gate = ConfidenceGate()
    policy = create_test_policy()

    decisions = [
        DeciderResult(
            question_id="Q1",
            qtype="choice",
            answer="real_bug_report",
            probs={"real_bug_report": 0.40, "low_effort": 0.35, "question": 0.25},
            confidence=0.30,
        )
    ]

    verdict = gate.evaluate(tool_name="apply_label", decisions=decisions, policy=policy)
    assert verdict.action == ActionKind.GUIDE
    assert verdict.band == Band.LOW
