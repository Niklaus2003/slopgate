"""Confidence Band Mathematics (Standalone Pattern Component).

Converts raw probabilities from Strands Decider 2B into normalized confidence bands:
- HIGH: Auto-execution eligible
- MEDIUM: Human confirmation recommended
- LOW / UNCERTAIN: Needs escalation, guidance, or denied

No external dependencies outside the standard library.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum


class Band(str, Enum):
    """Calibrated confidence bands."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def compute_choice_confidence(
    probs: Sequence[float] | dict[str, float],
    num_options: int | None = None,
) -> float:
    """Compute normalized confidence for categorical choice questions.

    Formula: (N * max(P) - 1) / (N - 1)
    Normalizes so that uniform guessing (1/N) yields 0.0, and certainty (1.0) yields 1.0.
    """
    if isinstance(probs, dict):
        prob_values = list(probs.values())
        n = num_options if num_options is not None else len(probs)
    else:
        prob_values = list(probs)
        n = num_options if num_options is not None else len(prob_values)

    if n <= 1:
        return 1.0

    p_max = max(prob_values) if prob_values else 0.0
    normalized = (n * p_max - 1.0) / (n - 1.0)
    return max(0.0, min(1.0, float(normalized)))


def classify_choice_band(
    confidence: float,
    high_at_least: float = 0.80,
    medium_at_least: float = 0.50,
) -> Band:
    """Classify normalized choice confidence into HIGH, MEDIUM, or LOW band."""
    if confidence >= high_at_least:
        return Band.HIGH
    if confidence >= medium_at_least:
        return Band.MEDIUM
    return Band.LOW


def classify_noul_band(
    p_true: float,
    true_at_least: float = 0.85,
    false_at_most: float = 0.15,
) -> tuple[Band, bool | None]:
    """Classify binary noul probability into confidence band and answer polarity.

    Returns:
        (Band.HIGH, True)  if p_true >= true_at_least
        (Band.HIGH, False) if p_true <= false_at_most
        (Band.LOW, None)   if uncertain (false_at_most < p_true < true_at_least)
    """
    if p_true >= true_at_least:
        return Band.HIGH, True
    if p_true <= false_at_most:
        return Band.HIGH, False
    return Band.LOW, None
