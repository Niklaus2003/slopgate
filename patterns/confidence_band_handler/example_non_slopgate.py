"""Non-SlopGate Reusable Pattern Demonstration: CRM & Customer Support Agent.

Proves the reusability of ConfidenceBandHandler on a completely different domain:
Gating automated emails (`send_email`) and destructive database mutations (`delete_record`).

Domain: Enterprise Customer Support Assistant
Tools:
  - search_knowledge_base(query) -> Read-only safe tool
  - send_email(recipient, subject, body) -> Gated by model confidence on user intent
  - delete_record(user_id, table) -> Destructive tool (Hardcoded Safety Invariant -> Always Confirm)

Run directly:
  python patterns/confidence_band_handler/example_non_slopgate.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add pattern directory to sys.path if run directly
pattern_dir = Path(__file__).resolve().parent
if str(pattern_dir) not in sys.path:
    sys.path.insert(0, str(pattern_dir))

try:
    from patterns.confidence_band_handler.gate import (
        ConfidenceGate,
        DeciderResult,
        SimplePolicy,
        ToolPolicy,
    )
    from patterns.confidence_band_handler.handler import AgentContext, ConfidenceBandHandler
except ImportError:
    from gate import ConfidenceGate, DeciderResult, SimplePolicy, ToolPolicy  # type: ignore[no-redef]
    from handler import AgentContext, ConfidenceBandHandler  # type: ignore[no-redef]
from strands.interventions import Confirm, Guide, Proceed


def run_crm_support_demo() -> None:
    print("=" * 70)
    print("  Enterprise Support Agent — ConfidenceBandHandler Gating Demo")
    print("=" * 70)

    # 1. Define Policy
    # - send_email requires a primary intent classification ('email_intent')
    # - search_kb always proceeds
    # - delete_record is destructive (built-in safety invariant forces Confirm)
    policy = SimplePolicy(
        high_at_least=0.80,
        medium_at_least=0.50,
        tools_gated={
            "send_email": ToolPolicy(requires=["email_intent"]),
            "search_kb": ToolPolicy(always="proceed"),
            "delete_record": ToolPolicy(requires=["user_intent"]),
        },
        routing={
            "request_invoice": {
                "high": "proceed",
                "medium": "confirm",
                "low": "deny",
            },
            "unclear_inquiry": {
                "high": "guide",
                "medium": "guide",
                "low": "guide",
            },
            "gdpr_erasure": {
                "high": "confirm",
                "medium": "confirm",
                "low": "deny",
            },
        },
    )

    gate = ConfidenceGate(policy=policy)

    # --------------------------------------------------------------------------
    # Scenario 1: High-Confidence Routine Request (Auto-Proceed)
    # User: "Please email me a copy of my March billing receipt."
    # --------------------------------------------------------------------------
    print("\n[Scenario 1] High-Confidence Routine Request")
    print("  User Input:   'Please email me my March invoice receipt.'")

    invoice_context = AgentContext(
        identifier="ticket#1042",
        results=[
            DeciderResult(
                question_id="email_intent",
                qtype="choice",
                answer="request_invoice",
                probs={"request_invoice": 0.94, "unclear_inquiry": 0.04, "other": 0.02},
                confidence=0.91,
            )
        ],
    )

    handler_1 = ConfidenceBandHandler(
        gate=gate,
        context_provider=lambda: invoice_context,
        policy=policy,
    )

    class MockSendEmailEvent:
        tool_name = "send_email"

    action_1 = handler_1.before_tool_call(MockSendEmailEvent())
    print("  Tool Proposed: send_email()")
    print(f"  Gate Verdict:  {type(action_1).__name__}")
    print(f"  Audit Rationale: {action_1.reason}")
    assert isinstance(action_1, Proceed), "Expected Proceed for high-confidence invoice email"
    print("  ==> Auto-executed safely without bothering human agents.")

    # --------------------------------------------------------------------------
    # Scenario 2: Ambiguous / Low-Confidence Inquiry (Guide / Clarify)
    # User: "I might want to close or change something, not sure what..."
    # --------------------------------------------------------------------------
    print("\n[Scenario 2] Ambiguous / Low-Confidence Inquiry")
    print("  User Input:   'I might want to close or change something, not sure...'")

    ambiguous_context = AgentContext(
        identifier="ticket#1043",
        results=[
            DeciderResult(
                question_id="email_intent",
                qtype="choice",
                answer="unclear_inquiry",
                probs={"request_invoice": 0.35, "unclear_inquiry": 0.40, "other": 0.25},
                confidence=0.10,
            )
        ],
    )

    handler_2 = ConfidenceBandHandler(
        gate=gate,
        context_provider=lambda: ambiguous_context,
        policy=policy,
    )

    action_2 = handler_2.before_tool_call(MockSendEmailEvent())
    print("  Tool Proposed: send_email()")
    print(f"  Gate Verdict:  {type(action_2).__name__}")
    print(f"  Guidance Sent: {getattr(action_2, 'feedback', action_2.reason)}")
    assert isinstance(action_2, (Guide, Confirm)), "Expected Guide/Confirm for ambiguous inquiry"
    print("  ==> Gated! Prevented agent from sending unintended emails; guided to ask user.")

    # --------------------------------------------------------------------------
    # Scenario 3: Destructive Action (Hardcoded Safety Invariant)
    # User: "Delete my user account and all personal order history under GDPR."
    # Decider Confidence: 99% HIGH
    # --------------------------------------------------------------------------
    print("\n[Scenario 3] Destructive Action (Hardcoded Safety Invariant)")
    print("  User Input:   'Delete my user account and records permanently under GDPR.'")

    deletion_context = AgentContext(
        identifier="ticket#1044",
        results=[
            DeciderResult(
                question_id="user_intent",
                qtype="choice",
                answer="gdpr_erasure",
                probs={"gdpr_erasure": 0.99, "other": 0.01},
                confidence=0.98,  # Extremely high confidence!
            )
        ],
    )

    handler_3 = ConfidenceBandHandler(
        gate=gate,
        context_provider=lambda: deletion_context,
        policy=policy,
    )

    class MockDeleteRecordEvent:
        tool_name = "delete_record"

    action_3 = handler_3.before_tool_call(MockDeleteRecordEvent())
    print("  Tool Proposed: delete_record()")
    print(f"  Gate Verdict:  {type(action_3).__name__}")
    print(f"  Prompt to Human: {getattr(action_3, 'prompt', action_3.reason)}")
    assert isinstance(action_3, Confirm), "Expected Confirm for destructive operation"
    print("  ==> Safety Invariant Preserved: Destructive operations NEVER auto-proceed, even at 99% confidence.")

    print("\n" + "=" * 70)
    print("  [SUCCESS] All 3 non-SlopGate enterprise scenarios verified successfully!")
    print("=" * 70)


if __name__ == "__main__":
    run_crm_support_demo()
