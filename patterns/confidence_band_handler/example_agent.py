"""Example demonstrating how to attach ConfidenceBandHandler to a Strands Agent.

This demonstrates the pattern in isolation:
1. Define a tool
2. Define current context with Decider results
3. Instantiate ConfidenceGate and ConfidenceBandHandler
4. Attach to Agent
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add pattern directory to sys.path if run directly
pattern_dir = Path(__file__).parent
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


def run_example() -> None:
    print("=== Reusable Decision Pattern: ConfidenceBandHandler ===")

    # 1. Configure policy
    policy = SimplePolicy(
        high_at_least=0.80,
        medium_at_least=0.50,
        tools_gated={
            "apply_label": ToolPolicy(requires=["Q1"]),
            "close_item": ToolPolicy(always="confirm"),
        },
        routing={
            "real_bug_report": {"high": "proceed", "medium": "confirm", "low": "confirm"},
        },
    )

    # 2. Mock decider result (high confidence bug report)
    decider_results = [
        DeciderResult(
            question_id="Q1",
            qtype="choice",
            answer="real_bug_report",
            probs={"real_bug_report": 0.95, "other": 0.05},
            confidence=0.90,
        )
    ]

    current_context = AgentContext(
        identifier="issue#42",
        results=decider_results,
    )

    # 3. Instantiate ConfidenceGate and ConfidenceBandHandler
    gate = ConfidenceGate(policy=policy)
    handler = ConfidenceBandHandler(
        gate=gate,
        context_provider=lambda: current_context,
        policy=policy,
    )

    # 4. Simulate agent attempting to call apply_label
    class MockEvent:
        tool_name = "apply_label"

    action = handler.before_tool_call(MockEvent())
    print(f"Tool 'apply_label' intervention outcome: {type(action).__name__}")
    assert type(action).__name__ == "Proceed", "Expected Proceed for high-confidence bug report"

    # 5. Simulate agent attempting to call close_item
    class MockCloseEvent:
        tool_name = "close_item"

    close_action = handler.before_tool_call(MockCloseEvent())
    print(f"Tool 'close_item' intervention outcome: {type(close_action).__name__}")
    assert type(close_action).__name__ == "Confirm", "Expected Confirm for close_item safety invariant"

    print("Pattern example executed successfully! Zero violations.")


if __name__ == "__main__":
    run_example()
