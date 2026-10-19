"""Unit tests for confidence band mathematics and classification."""

import pytest

from slopgate.config import PolicyConfig
from slopgate.models import Band, DeciderResult, Question
from slopgate.policy.bands import (
    classify,
    classify_choice,
    classify_noul,
    compute_choice_confidence,
)


def test_compute_choice_confidence_uniform():
    # Uniform across 4 options: p_max = 0.25 -> confidence should be 0.0
    probs = {"a": 0.25, "b": 0.25, "c": 0.25, "d": 0.25}
    assert pytest.approx(compute_choice_confidence(probs), abs=1e-5) == 0.0


def test_compute_choice_confidence_certain():
    # Certain: p_max = 1.0 -> confidence should be 1.0
    probs = {"a": 1.0, "b": 0.0, "c": 0.0}
    assert pytest.approx(compute_choice_confidence(probs), abs=1e-5) == 1.0


def test_compute_choice_confidence_intermediate():
    # 3 options: p_max = 0.6 -> (3 * 0.6 - 1) / (3 - 1) = (1.8 - 1) / 2 = 0.4
    probs = {"a": 0.6, "b": 0.3, "c": 0.1}
    assert pytest.approx(compute_choice_confidence(probs), abs=1e-5) == 0.4


def test_classify_choice_thresholds():
    assert classify_choice(0.85, high_at_least=0.80, medium_at_least=0.50) == Band.HIGH
    assert classify_choice(0.80, high_at_least=0.80, medium_at_least=0.50) == Band.HIGH
    assert classify_choice(0.79, high_at_least=0.80, medium_at_least=0.50) == Band.MEDIUM
    assert classify_choice(0.50, high_at_least=0.80, medium_at_least=0.50) == Band.MEDIUM
    assert classify_choice(0.49, high_at_least=0.80, medium_at_least=0.50) == Band.LOW
    assert classify_choice(0.00, high_at_least=0.80, medium_at_least=0.50) == Band.LOW


def test_classify_noul_asymmetric_thresholds():
    # Confident true: P >= 0.85
    band, outcome = classify_noul(0.92, true_at_least=0.85, false_at_most=0.15)
    assert band == Band.HIGH
    assert outcome is True

    # Confident false: P <= 0.15
    band, outcome = classify_noul(0.08, true_at_least=0.85, false_at_most=0.15)
    assert band == Band.HIGH
    assert outcome is False

    # Uncertain / ambiguous: 0.15 < P < 0.85 (even if P=0.55 or P=0.49!)
    band, outcome = classify_noul(0.55, true_at_least=0.85, false_at_most=0.15)
    assert band == Band.LOW
    assert outcome is None

    band, outcome = classify_noul(0.75, true_at_least=0.85, false_at_most=0.15)
    assert band == Band.LOW
    assert outcome is None


def test_classify_dispatch():
    policy = PolicyConfig()
    q_choice = Question(id="Q1", qtype="choice", text="Kind?", options=("bug", "feature"))
    res_choice = DeciderResult(
        question_id="Q1",
        qtype="choice",
        answer="bug",
        probs={"bug": 0.95, "feature": 0.05},
    )
    band, answer = classify(q_choice, res_choice, policy)
    assert band == Band.HIGH
    assert answer == "bug"

    q_noul = Question(id="N1", qtype="noul", text="Has repro?")
    res_noul = DeciderResult(
        question_id="N1",
        qtype="noul",
        answer=True,
        probs={"true": 0.90, "false": 0.10},
    )
    band, outcome = classify(q_noul, res_noul, policy)
    assert band == Band.HIGH
    assert outcome is True
