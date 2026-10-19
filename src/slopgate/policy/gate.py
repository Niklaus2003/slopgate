"""ConfidenceGate policy evaluation engine.

Implements the 4-way action gating: Proceed, Confirm, Guide, Deny.
Enforces hardcoded safety invariants in pure Python code (02_CONSTRAINTS.md).
Follows: architecture.md §6.5, problem-statement.md §8.2.
"""

from __future__ import annotations

from typing import Any

from slopgate.config import PolicyConfig
from slopgate.models import ActionKind, Band, DeciderResult, GateVerdict
from slopgate.policy.bands import classify_choice, classify_noul, compute_choice_confidence


class ConfidenceGate:
    """Core decision gate evaluating proposed tool calls against Decider results."""

    def evaluate(
        self,
        tool_name: str,
        decisions: list[DeciderResult],
        policy: PolicyConfig,
        context: dict[str, Any] | None = None,
    ) -> GateVerdict:
        """Evaluate a proposed tool call and emit a GateVerdict.

        Hard Rules in Code (cannot be overridden by policy.yaml):
        1. close_item is NEVER Proceed or Proceed-soft; always CONFIRM.
        2. security_report is at least CONFIRM; never Proceed.
        3. Any tool not listed in policy.tools_gated is CONFIRM.
        """
        # Hard Rule 1: close_item can NEVER auto-execute
        if tool_name == "close_item":
            return GateVerdict(
                question_id="SAFETY_INVARIANT_CLOSE",
                band=Band.HIGH,
                action=ActionKind.CONFIRM,
                reason="INVARIANT 1: Automated closing of issues/PRs is prohibited. Maintainer confirmation required.",
                is_soft=False,
            )

        # Hard Rule 3: Unlisted tools require human confirmation
        if tool_name not in policy.tools_gated:
            return GateVerdict(
                question_id="SAFETY_UNLISTED_TOOL",
                band=Band.MEDIUM,
                action=ActionKind.CONFIRM,
                reason=f"Tool '{tool_name}' is not declared in policy.tools_gated; defaulting to maintainer confirmation.",
                is_soft=False,
            )

        tool_gate = policy.tools_gated[tool_name]

        # Check if tool is statically configured to always confirm/deny
        if tool_gate.always:
            always_action = ActionKind(tool_gate.always.lower())
            return GateVerdict(
                question_id="TOOL_POLICY_ALWAYS",
                band=Band.HIGH,
                action=always_action,
                reason=f"Tool '{tool_name}' is configured as always '{tool_gate.always}'.",
                is_soft=False,
            )

        # Index decisions by question_id
        decisions_by_id = {d.question_id: d for d in decisions}

        # Check required decisions
        for req_q in tool_gate.requires:
            if req_q not in decisions_by_id:
                # Also check prefix match (e.g. "Q1" matching "Q1" or "Q1_issue_kind")
                match = any(qid.startswith(req_q) for qid in decisions_by_id)
                if not match:
                    return GateVerdict(
                        question_id=req_q,
                        band=Band.LOW,
                        action=ActionKind.CONFIRM,
                        reason=f"Missing required decision '{req_q}' for tool '{tool_name}'.",
                        is_soft=False,
                    )

        # Locate primary Q1 classification result
        q1_result = None
        for qid, res in decisions_by_id.items():
            if qid == "Q1" or qid.startswith("Q1"):
                q1_result = res
                break

        if not q1_result:
            return GateVerdict(
                question_id="UNKNOWN",
                band=Band.LOW,
                action=ActionKind.CONFIRM,
                reason="No classification decision available.",
                is_soft=False,
            )

        # Compute Q1 band
        conf = (
            q1_result.confidence
            if q1_result.confidence is not None
            else compute_choice_confidence(q1_result.probs)
        )
        q1_band = classify_choice(
            conf,
            high_at_least=policy.bands.choice.high_at_least,
            medium_at_least=policy.bands.choice.medium_at_least,
        )

        item_kind = str(q1_result.answer)

        # Hard Rule 2: Security reports must never proceed autonomously
        if item_kind == "security_report":
            return GateVerdict(
                question_id=q1_result.question_id,
                band=q1_band,
                action=ActionKind.CONFIRM,
                reason="INVARIANT: Security reports require maintainer review and private disclosure handling.",
                is_soft=False,
            )

        # Evaluate routing table from policy
        routing_cfg = policy.routing.get(item_kind)
        if not routing_cfg:
            return GateVerdict(
                question_id=q1_result.question_id,
                band=q1_band,
                action=ActionKind.CONFIRM,
                reason=f"No routing rule for item kind '{item_kind}'.",
                is_soft=False,
            )

        # High confidence path
        if q1_band is Band.HIGH:
            # Special conditional handling for bug reports with N1 repro check
            if item_kind == "real_bug_report" and "N1" in decisions_by_id:
                n1_res = decisions_by_id["N1"]
                p_true = n1_res.probs.get("true", 0.5)
                _n1_band, n1_outcome = classify_noul(
                    p_true,
                    true_at_least=policy.bands.noul.true_at_least,
                    false_at_most=policy.bands.noul.false_at_most,
                )
                if n1_outcome is True:
                    # Confident bug with repro
                    return GateVerdict(
                        question_id=q1_result.question_id,
                        band=Band.HIGH,
                        action=ActionKind.PROCEED,
                        reason="Confirmed bug report with verified reproduction steps.",
                        is_soft=False,
                    )
                if n1_outcome is False:
                    # Confident bug but lacking repro steps -> soft proceed (needs-info)
                    return GateVerdict(
                        question_id="N1",
                        band=Band.HIGH,
                        action=ActionKind.PROCEED_SOFT,
                        reason="Bug report lacks reproduction steps; applying needs-info.",
                        is_soft=True,
                    )
                # N1 uncertain -> guide/confirm
                return GateVerdict(
                    question_id="N1",
                    band=Band.LOW,
                    action=ActionKind.GUIDE,
                    reason="Reproduction steps unclear; escalating to Bedrock for analysis.",
                    is_soft=False,
                )

            # Map high-confidence action from routing config
            raw_action = routing_cfg.high.lower()
            if raw_action == "proceed_soft":
                verdict_action = ActionKind.PROCEED_SOFT
                is_soft = True
            elif raw_action == "proceed":
                verdict_action = ActionKind.PROCEED
                is_soft = False
            elif raw_action == "confirm":
                verdict_action = ActionKind.CONFIRM
                is_soft = False
            elif raw_action == "guide":
                verdict_action = ActionKind.GUIDE
                is_soft = False
            else:
                verdict_action = ActionKind.DENY
                is_soft = False

            return GateVerdict(
                question_id=q1_result.question_id,
                band=Band.HIGH,
                action=verdict_action,
                reason=f"High confidence ({conf:.2f}) {item_kind}; routed to {verdict_action.value}.",
                is_soft=is_soft,
            )

        # Medium confidence path
        if q1_band is Band.MEDIUM:
            return GateVerdict(
                question_id=q1_result.question_id,
                band=Band.MEDIUM,
                action=ActionKind.CONFIRM,
                reason=f"Medium confidence ({conf:.2f}) {item_kind}; queued for maintainer review.",
                is_soft=False,
            )

        # Low confidence path
        return GateVerdict(
            question_id=q1_result.question_id,
            band=Band.LOW,
            action=ActionKind.GUIDE,
            reason=f"Low confidence ({conf:.2f}) {item_kind}; escalating to Bedrock for reasoning.",
            is_soft=False,
        )
