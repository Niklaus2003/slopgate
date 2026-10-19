"""DeciderClient protocol and FakeDecider test double.

Enables 100% offline, model-free unit testing.
Follows: architecture.md §6.3.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from slopgate.models import DeciderResult, Question, State
from slopgate.policy.bands import compute_choice_confidence


class DeciderUnavailable(Exception):
    """Raised when the Decider model or inference service cannot be reached."""


@runtime_checkable
class DeciderClient(Protocol):
    """Standard interface for Decider inference engines."""

    model_id: str

    def ask(self, state: State, questions: list[Question]) -> list[DeciderResult]:
        """Ask one or more typed questions against the bounded state."""
        ...


class FakeDecider:
    """Deterministic, scripted test double implementing DeciderClient.

    Requires zero GPU, zero neural weights download, and zero external I/O.
    """

    def __init__(
        self,
        model_id: str = "fake-decider-2b",
        canned_responses: dict[str, DeciderResult] | None = None,
        latency_ms: float = 5.0,
    ) -> None:
        self.model_id = model_id
        self.canned_responses = canned_responses or {}
        self.latency_ms = latency_ms
        self.call_count = 0

    def ask(self, state: State, questions: list[Question]) -> list[DeciderResult]:
        """Evaluate questions against state text deterministically."""
        self.call_count += 1
        results: list[DeciderResult] = []
        text_lower = state.text.lower()

        for q in questions:
            # Check explicit canned overrides first
            if q.id in self.canned_responses:
                results.append(self.canned_responses[q.id])
                continue

            if q.qtype == "choice":
                # Default options
                opts = list(q.options) or [
                    "real_bug_report",
                    "feature_request",
                    "support_question",
                    "likely_duplicate",
                    "security_report",
                    "low_effort",
                ]

                # Deterministic classification based on state content
                if any(w in text_lower for w in ["vulnerability", "exploit", "cve", "security", "rce"]):
                    winner = "security_report" if "security_report" in opts else opts[0]
                    probs = {opt: (0.90 if opt == winner else 0.10 / (len(opts) - 1)) for opt in opts}
                elif any(w in text_lower for w in ["[rejected ai]", "rejected ai", "ai junk", "spam", "low effort", "plz fix", "empty body"]):
                    winner = "low_effort" if "low_effort" in opts else opts[0]
                    probs = {opt: (0.85 if opt == winner else 0.15 / (len(opts) - 1)) for opt in opts}
                elif any(w in text_lower for w in ["how do i", "how to", "question", "support"]):
                    winner = "support_question" if "support_question" in opts else opts[0]
                    probs = {opt: (0.88 if opt == winner else 0.12 / (len(opts) - 1)) for opt in opts}
                elif any(w in text_lower for w in ["duplicate of #", "same as #", "is a duplicate"]):
                    winner = "likely_duplicate" if "likely_duplicate" in opts else opts[0]
                    probs = {opt: (0.86 if opt == winner else 0.14 / (len(opts) - 1)) for opt in opts}
                elif "ready_for_review" in opts and any(w in text_lower for w in ["docs:", "fix", "drop support", "test", "merged: true"]):
                    winner = "ready_for_review"
                    probs = {opt: (0.88 if opt == winner else 0.12 / (len(opts) - 1)) for opt in opts}
                elif "out_of_scope" in opts and any(w in text_lower for w in ["cloudflare", "unmerged", "rst parses"]):
                    winner = "out_of_scope"
                    probs = {opt: (0.82 if opt == winner else 0.18 / (len(opts) - 1)) for opt in opts}
                elif "ambiguous" in text_lower or "uncertain" in text_lower:
                    # Low confidence distribution
                    winner = opts[0]
                    p_spread = 1.0 / len(opts)
                    probs = {opt: (p_spread + 0.05 if opt == winner else p_spread - 0.05 / (len(opts) - 1)) for opt in opts}
                elif "medium" in text_lower:
                    # Medium confidence distribution
                    winner = "real_bug_report" if "real_bug_report" in opts else opts[0]
                    probs = {opt: (0.60 if opt == winner else 0.40 / (len(opts) - 1)) for opt in opts}
                else:
                    # Default: high confidence bug report or ready PR
                    winner = "real_bug_report" if "real_bug_report" in opts else opts[0]
                    probs = {opt: (0.92 if opt == winner else 0.08 / (len(opts) - 1)) for opt in opts}

                conf = compute_choice_confidence(probs)
                results.append(
                    DeciderResult(
                        question_id=q.id,
                        qtype="choice",
                        answer=winner,
                        probs=probs,
                        confidence=conf,
                        latency_ms=self.latency_ms,
                        model_id=self.model_id,
                        from_cache=False,
                    )
                )

            elif q.qtype == "noul":
                # Boolean question
                if "no repro" in text_lower or "missing repro" in text_lower or "low effort" in text_lower:
                    p_true = 0.06
                elif "repro" in text_lower or "traceback" in text_lower or "steps" in text_lower:
                    p_true = 0.94
                elif "ambiguous" in text_lower:
                    p_true = 0.52
                else:
                    p_true = 0.88

                results.append(
                    DeciderResult(
                        question_id=q.id,
                        qtype="noul",
                        answer=bool(p_true >= 0.5),
                        probs={"true": p_true, "false": round(1.0 - p_true, 4)},
                        confidence=None,
                        latency_ms=self.latency_ms,
                        model_id=self.model_id,
                        from_cache=False,
                    )
                )

        return results
