"""Unit tests for SlopGate domain models."""

from slopgate.models import (
    ActionKind,
    ActionPlan,
    Band,
    DeciderResult,
    Facts,
    GateVerdict,
    Item,
    PlannedToolCall,
    Question,
    State,
)


def test_item_creation_and_properties():
    item = Item(
        repo="pallets/flask",
        number=1234,
        type="issue",
        title="Session cookie bug",
        body="Steps to reproduce...",
        raw={"id": 999},
    )
    assert item.id == "pallets/flask#1234"
    assert item.status == "queued"
    assert item.type == "issue"


def test_facts_and_state():
    facts = Facts(
        cited_paths_found=(2, 2),
        has_code_block=True,
        has_repro_heading=True,
        template_filled=(3, 3),
        links_to_issue=[100],
        ci_status="passing",
        candidate_duplicate=(50, 0.82),
        contributing_excerpt="Follow PEP 8",
    )
    state = State(
        text="[TYPE] issue\n[TITLE] Bug",
        hash="abc123hash",
        approx_tokens=150,
        facts=facts,
    )
    assert state.facts.has_code_block is True
    assert state.approx_tokens == 150
    assert state.facts.candidate_duplicate == (50, 0.82)


def test_question_and_decider_result():
    q = Question(
        id="Q1",
        qtype="choice",
        text="Which category fits this item?",
        options=("real_bug_report", "low_effort"),
    )
    assert q.id == "Q1"
    assert len(q.options) == 2

    res = DeciderResult(
        question_id="Q1",
        qtype="choice",
        answer="real_bug_report",
        probs={"real_bug_report": 0.90, "low_effort": 0.10},
        confidence=0.80,
        latency_ms=12.5,
        model_id="test-model",
    )
    assert res.confidence == 0.80
    assert res.answer == "real_bug_report"
    assert res.from_cache is False


def test_gate_verdict_and_action_plan():
    verdict = GateVerdict(
        question_id="Q1",
        band=Band.HIGH,
        action=ActionKind.PROCEED,
        reason="Clear bug report with high confidence",
    )
    assert verdict.action == ActionKind.PROCEED
    assert verdict.band == Band.HIGH
    assert verdict.is_soft is False

    tool_call = PlannedToolCall(
        tool_name="apply_label",
        args={"label": "triaged"},
        idempotency_key="flask#123:label:triaged",
    )

    plan = ActionPlan(
        steps=[tool_call],
        overall=ActionKind.PROCEED,
        suggested_labels=["triaged"],
        receipt_notes=["Auto-labeled triaged"],
    )
    assert plan.overall == ActionKind.PROCEED
    assert len(plan.steps) == 1
    assert plan.needs_bedrock_draft is False
