"""Unit tests for ConfidenceBandHandler (Strands InterventionHandler adapter)."""

from __future__ import annotations

import pytest
from strands.interventions import Confirm, Guide, Proceed

from slopgate.agent.handler import ConfidenceBandHandler, ItemContext
from slopgate.config import load_policy
from slopgate.models import DeciderResult, Item
from slopgate.policy.gate import ConfidenceGate


@pytest.fixture
def policy():
    return load_policy()


@pytest.fixture
def gate():
    return ConfidenceGate()


@pytest.fixture
def base_item() -> Item:
    return Item(
        repo="pallets/flask",
        number=42,
        type="issue",
        title="Valid bug report",
        body="Traceback on Werkzeug router failure",
        created_at="2026-10-15T10:00:00Z",
    )


class MockEvent:
    def __init__(self, tool_name: str, args: dict | None = None) -> None:
        self.tool_use = {"name": tool_name, "input": args or {}}
        self.tool_name = tool_name


def test_handler_proceed_on_high_confidence(gate, policy, base_item):
    results = [
        DeciderResult(
            question_id="Q1",
            qtype="choice",
            answer="real_bug_report",
            probs={"real_bug_report": 0.95, "other": 0.05},
            confidence=0.90,
        )
    ]
    ctx = ItemContext(item=base_item, results=results)
    handler = ConfidenceBandHandler(gate=gate, context_provider=lambda: ctx, policy=policy)

    event = MockEvent("apply_label", {"label": "bug"})
    action = handler.before_tool_call(event)

    assert isinstance(action, Proceed)
    assert len(ctx.audit_trail) == 1
    assert ctx.audit_trail[0]["action"] == "proceed"
    assert ctx.audit_trail[0]["band"] == "high"


def test_handler_confirm_on_medium_confidence(gate, policy, base_item):
    results = [
        DeciderResult(
            question_id="Q1",
            qtype="choice",
            answer="real_bug_report",
            probs={"real_bug_report": 0.80, "other": 0.20},
            confidence=0.60,  # Below 0.80 high threshold
        )
    ]
    ctx = ItemContext(item=base_item, results=results)
    handler = ConfidenceBandHandler(gate=gate, context_provider=lambda: ctx, policy=policy)

    event = MockEvent("apply_label", {"label": "bug"})
    action = handler.before_tool_call(event)

    assert isinstance(action, Confirm)
    assert ctx.audit_trail[0]["action"] == "confirm"
    assert ctx.audit_trail[0]["band"] == "medium"


def test_handler_guide_on_ambiguity(gate, policy, base_item):
    results = [
        DeciderResult(
            question_id="Q1",
            qtype="choice",
            answer="real_bug_report",
            probs={"real_bug_report": 0.52, "other": 0.48},
            confidence=0.04,  # LOW band
        )
    ]
    ctx = ItemContext(item=base_item, results=results)
    handler = ConfidenceBandHandler(gate=gate, context_provider=lambda: ctx, policy=policy)

    event = MockEvent("apply_label", {"label": "bug"})
    action = handler.before_tool_call(event)

    assert isinstance(action, (Guide, Confirm))
    assert ctx.audit_trail[0]["band"] == "low"


def test_close_item_provably_never_proceeds(gate, policy, base_item):
    """CRITICAL SAFETY INVARIANT TEST:

    close_item must NEVER return Proceed even with 100% confidence.
    """
    results = [
        DeciderResult(
            question_id="Q1",
            qtype="choice",
            answer="low_effort",
            probs={"low_effort": 1.0},
            confidence=1.0,
        )
    ]
    ctx = ItemContext(item=base_item, results=results)
    handler = ConfidenceBandHandler(gate=gate, context_provider=lambda: ctx, policy=policy)

    event = MockEvent("close_item", {"reason": "Low effort item"})
    action = handler.before_tool_call(event)

    assert not isinstance(action, Proceed)
    assert isinstance(action, Confirm)
    assert "INVARIANT" in action.reason


def test_handler_unlisted_tool_defaults_to_confirm(gate, policy, base_item):
    results = [
        DeciderResult(
            question_id="Q1",
            qtype="choice",
            answer="real_bug_report",
            probs={"real_bug_report": 0.95},
            confidence=0.90,
        )
    ]
    ctx = ItemContext(item=base_item, results=results)
    handler = ConfidenceBandHandler(gate=gate, context_provider=lambda: ctx, policy=policy)

    event = MockEvent("unregistered_arbitrary_tool")
    action = handler.before_tool_call(event)

    assert isinstance(action, Confirm)
    assert "not declared" in action.reason
