"""Confidence band mathematics for Strands Decider 2B.

Follows: problem-statement.md §4 & §8.1, architecture.md §6.5.
Pure functions, zero I/O, fully testable.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from slopgate.config import PolicyConfig
from slopgate.models import Band, DeciderResult, Question


def compute_choice_confidence(probs: Mapping[str, float] | list[float]) -> float:
    """Compute normalized confidence for choice questions.

    Formula from Strands Decider 2B:
        confidence = (N * p_max - 1) / (N - 1)

    Properties:
        - 0.0 for uniform distribution (p_max = 1/N)
        - 1.0 for certain distribution (p_max = 1.0)
        - Comparable across different N (e.g. 3 vs 5 vs 10 options)
    """
    if isinstance(probs, Mapping):
        values = list(probs.values())
    else:
        values = list(probs)

    n = len(values)
    if n <= 1:
        return 1.0

    p_max = max(values)
    conf = (n * p_max - 1.0) / (n - 1.0)
    # Clamp to [0.0, 1.0] to protect against floating point rounding
    return max(0.0, min(1.0, float(conf)))


def classify_choice(
    confidence: float,
    high_at_least: float = 0.80,
    medium_at_least: float = 0.50,
) -> Band:
    """Classify choice question normalized confidence into Band.HIGH, MEDIUM, or LOW."""
    if confidence >= high_at_least:
        return Band.HIGH
    if confidence >= medium_at_least:
        return Band.MEDIUM
    return Band.LOW


classify_choice_band = classify_choice


def classify_noul(
    p_true: float,
    true_at_least: float = 0.85,
    false_at_most: float = 0.15,
) -> tuple[Band, bool | None]:
    """Classify yes/no (noul) probability into (Band, outcome).

    Returns:
        (Band.HIGH, True)  if p_true >= true_at_least (confident yes)
        (Band.HIGH, False) if p_true <= false_at_most (confident no)
        (Band.LOW, None)   if in between (uncertain)
    """
    if p_true >= true_at_least:
        return Band.HIGH, True
    if p_true <= false_at_most:
        return Band.HIGH, False
    return Band.LOW, None


def classify(
    question: Question,
    result: DeciderResult,
    policy: PolicyConfig,
) -> tuple[Band, Any]:
    """General classifier applying policy thresholds to a DeciderResult."""
    if result.qtype == "choice":
        conf = (
            result.confidence
            if result.confidence is not None
            else compute_choice_confidence(result.probs)
        )
        band = classify_choice(
            conf,
            high_at_least=policy.bands.choice.high_at_least,
            medium_at_least=policy.bands.choice.medium_at_least,
        )
        return band, result.answer

    if result.qtype == "noul":
        # Extract p_true from probabilities dict
        p_true = result.probs.get("true", 0.5)
        band, outcome = classify_noul(
            p_true,
            true_at_least=policy.bands.noul.true_at_least,
            false_at_most=policy.bands.noul.false_at_most,
        )
        return band, outcome

    raise ValueError(f"Unknown question type: {result.qtype}")
