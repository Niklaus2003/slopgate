"""Unit tests for standalone ConfidenceBandHandler pattern."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure pattern directory is on sys.path
pattern_dir = Path(__file__).resolve().parent.parent
if str(pattern_dir) not in sys.path:
    sys.path.insert(0, str(pattern_dir))

try:
    from patterns.confidence_band_handler.bands import (
        Band,
        classify_choice_band,
        classify_noul_band,
        compute_choice_confidence,
    )
    from patterns.confidence_band_handler.gate import (
        DEFAULT_DESTRUCTIVE_TOOLS,
        ActionKind,
        ConfidenceGate,
        DeciderResult,
        SimplePolicy,
        ToolPolicy,
        load_policy_from_yaml,
    )
    from patterns.confidence_band_handler.handler import AgentContext, ConfidenceBandHandler
except ImportError:
    from bands import (  # type: ignore[no-redef]
        Band,
        classify_choice_band,
        classify_noul_band,
        compute_choice_confidence,
    )
    from gate import (  # type: ignore[no-redef]
        DEFAULT_DESTRUCTIVE_TOOLS,
        ActionKind,
        ConfidenceGate,
        DeciderResult,
        SimplePolicy,
        ToolPolicy,
        load_policy_from_yaml,
    )
    from handler import AgentContext, ConfidenceBandHandler  # type: ignore[no-redef]
from strands.interventions import Confirm, Deny, Guide, Proceed


def test_confidence_math():
    # 2 options: max prob 0.9 -> (2 * 0.9 - 1) / 1 = 0.8
    conf = compute_choice_confidence({"a": 0.9, "b": 0.1})
    assert round(conf, 4) == 0.8
    assert classify_choice_band(conf, high_at_least=0.80) == Band.HIGH
    assert classify_choice_band(0.60, high_at_least=0.80, medium_at_least=0.50) == Band.MEDIUM
    assert classify_choice_band(0.30, high_at_least=0.80, medium_at_least=0.50) == Band.LOW

    # noul math
    band, val = classify_noul_band(0.92, true_at_least=0.85)
    assert band == Band.HIGH and val is True

    band, val = classify_noul_band(0.08, false_at_most=0.15)
    assert band == Band.HIGH and val is False

    band, val = classify_noul_band(0.50, true_at_least=0.85, false_at_most=0.15)
    assert band == Band.LOW and val is None


def test_safety_invariants():
    gate = ConfidenceGate()
    # Built-in destructive tools are ALWAYS Confirm
    for tool in DEFAULT_DESTRUCTIVE_TOOLS:
        v = gate.evaluate(tool, [])
        assert v.action == ActionKind.CONFIRM
        assert "destructive" in v.reason.lower()

    # Prefix-based destructive tools
    for prefix_tool in ("delete_record", "drop_table", "wipe_disk"):
        v = gate.evaluate(prefix_tool, [])
        assert v.action == ActionKind.CONFIRM

    # unlisted tools default to Confirm
    v2 = gate.evaluate("unregistered_random_tool", [])
    assert v2.action == ActionKind.CONFIRM


def test_handler_interventions():
    policy = SimplePolicy(
        high_at_least=0.80,
        medium_at_least=0.50,
        tools_gated={"send_msg": ToolPolicy(requires=["Q1"])},
        routing={"alert": {"high": "proceed", "medium": "confirm", "low": "deny"}},
    )
    gate = ConfidenceGate(policy=policy)

    # 1. High confidence -> Proceed
    high_ctx = AgentContext(
        identifier="item#1",
        results=[
            DeciderResult(
                question_id="Q1",
                qtype="choice",
                answer="alert",
                probs={"alert": 0.95, "other": 0.05},
                confidence=0.90,
            )
        ],
    )
    h_high = ConfidenceBandHandler(gate, lambda: high_ctx, policy)
    res = h_high.before_tool_call(type("Event", (), {"tool_name": "send_msg"})())
    assert isinstance(res, Proceed)

    # 2. Medium confidence -> Confirm
    med_ctx = AgentContext(
        identifier="item#2",
        results=[
            DeciderResult(
                question_id="Q1",
                qtype="choice",
                answer="alert",
                probs={"alert": 0.80, "other": 0.20},
                confidence=0.60,
            )
        ],
    )
    h_med = ConfidenceBandHandler(gate, lambda: med_ctx, policy)
    res = h_med.before_tool_call(type("Event", (), {"tool_name": "send_msg"})())
    assert isinstance(res, Confirm)

    # 3. Low confidence -> Deny
    low_ctx = AgentContext(
        identifier="item#3",
        results=[
            DeciderResult(
                question_id="Q1",
                qtype="choice",
                answer="alert",
                probs={"alert": 0.55, "other": 0.45},
                confidence=0.10,
            )
        ],
    )
    h_low = ConfidenceBandHandler(gate, lambda: low_ctx, policy)
    res = h_low.before_tool_call(type("Event", (), {"tool_name": "send_msg"})())
    assert isinstance(res, Deny)

    # 4. close_item -> Confirm
    res_close = h_high.before_tool_call(type("Event", (), {"tool_name": "close_item"})())
    assert isinstance(res_close, Confirm)


def test_noul_binary_decision_gating():
    policy = SimplePolicy(
        true_at_least=0.85,
        false_at_most=0.15,
        tools_gated={"deploy_service": ToolPolicy(requires=["is_authorized"])},
        routing={"true": {"high": "proceed", "medium": "confirm", "low": "deny"}},
    )
    gate = ConfidenceGate(policy=policy)

    # High confidence True -> Proceed
    decisions = [
        DeciderResult(
            question_id="is_authorized",
            qtype="noul",
            answer=True,
            probs={"True": 0.95, "False": 0.05},
        )
    ]
    v = gate.evaluate("deploy_service", decisions)
    assert v.action == ActionKind.PROCEED
    assert v.band == Band.HIGH

    # Low confidence uncertain -> Deny / Confirm
    decisions_uncertain = [
        DeciderResult(
            question_id="is_authorized",
            qtype="noul",
            answer=True,
            probs={"True": 0.55, "False": 0.45},
        )
    ]
    v_unc = gate.evaluate("deploy_service", decisions_uncertain)
    assert v_unc.action == ActionKind.CONFIRM
    assert v_unc.band == Band.LOW


def test_load_policy_from_yaml():
    yaml_path = pattern_dir / "policy.example.yaml"
    assert yaml_path.is_file()

    policy = load_policy_from_yaml(yaml_path)
    assert policy.high_at_least == 0.80
    assert policy.medium_at_least == 0.50
    assert "apply_label" in policy.tools_gated
    assert "close_item" in policy.tools_gated
    assert policy.tools_gated["close_item"].always == "confirm"
    assert "real_bug_report" in policy.routing


def test_non_slopgate_crm_scenarios():
    policy = SimplePolicy(
        high_at_least=0.80,
        medium_at_least=0.50,
        tools_gated={
            "send_email": ToolPolicy(requires=["email_intent"]),
            "search_kb": ToolPolicy(always="proceed"),
            "delete_record": ToolPolicy(requires=["user_intent"]),
        },
        routing={
            "request_invoice": {"high": "proceed", "medium": "confirm", "low": "deny"},
            "unclear_inquiry": {"high": "guide", "medium": "guide", "low": "guide"},
        },
    )
    gate = ConfidenceGate(policy=policy)

    # 1. Invoice request -> Proceed
    ctx1 = AgentContext(
        identifier="crm#1",
        results=[
            DeciderResult(
                question_id="email_intent",
                qtype="choice",
                answer="request_invoice",
                probs={"request_invoice": 0.94, "unclear_inquiry": 0.06},
                confidence=0.88,
            )
        ],
    )
    h1 = ConfidenceBandHandler(gate, lambda: ctx1, policy)
    act1 = h1.before_tool_call(type("Event", (), {"tool_name": "send_email"})())
    assert isinstance(act1, Proceed)

    # 2. Unclear inquiry -> Guide
    ctx2 = AgentContext(
        identifier="crm#2",
        results=[
            DeciderResult(
                question_id="email_intent",
                qtype="choice",
                answer="unclear_inquiry",
                probs={"request_invoice": 0.4, "unclear_inquiry": 0.6},
                confidence=0.20,
            )
        ],
    )
    h2 = ConfidenceBandHandler(gate, lambda: ctx2, policy)
    act2 = h2.before_tool_call(type("Event", (), {"tool_name": "send_email"})())
    assert isinstance(act2, Guide)

    # 3. Destructive deletion -> Confirm
    ctx3 = AgentContext(
        identifier="crm#3",
        results=[
            DeciderResult(
                question_id="user_intent",
                qtype="choice",
                answer="delete_account",
                probs={"delete_account": 0.99, "other": 0.01},
                confidence=0.98,
            )
        ],
    )
    h3 = ConfidenceBandHandler(gate, lambda: ctx3, policy)
    act3 = h3.before_tool_call(type("Event", (), {"tool_name": "delete_record"})())
    assert isinstance(act3, Confirm)
