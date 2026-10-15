# Reusable Strands Decider 2B Decision Pattern: ConfidenceBandHandler

> **Pattern Tag:** `#policy`

A reusable, framework-independent decision gating pattern for AI agents. It evaluates proposed agent actions against a local decision model (**Strands Decider 2B**) with calibrated confidence thresholds before any sensitive tool call executes.

---

## What It Does
1. **Mathematical Confidence Bands:** Converts raw probability distributions from Strands Decider 2B into standardized confidence bands: `HIGH`, `MEDIUM`, and `LOW/UNCERTAIN`.
2. **Four-Way Action Gate:** Returns typed verdicts:
   - **`Proceed`**: High confidence; tool executes automatically.
   - **`Confirm`**: Medium confidence or policy-gated action; requires human approval.
   - **`Guide`**: Low confidence; routes agent to escalate for additional reasoning.
   - **`Deny`**: Policy violation or missing prerequisite decision; tool call is blocked.
3. **Domain Agnostic:** Zero GitHub or SlopGate dependencies. Can gate any tool in any agent framework (e.g., gating `send_email`, `delete_database_record`, or `refund_customer`).

---

## Quickstart (5 Minutes)

```python
from bands import classify_choice
from gate import ConfidenceGate

# Initialize gate with policy rules
gate = ConfidenceGate(policy_path="policy.example.yaml")

# Evaluate proposed tool call against decider results
verdict = gate.evaluate(
    tool_name="send_email",
    decisions=[...],  # DeciderResult objects
)

if verdict.action == "proceed":
    # Execute tool
    pass
elif verdict.action == "confirm":
    # Route to human review queue
    pass
```

---

## Status
Scaffolded in Phase 1. Core implementation, standalone tests, and toy agent example finalized in Phase 9.
