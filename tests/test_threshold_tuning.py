"""Unit tests for threshold tuning optimizer and held-out validation."""

from __future__ import annotations

from slopgate.backtest.tuning import evaluate_thresholds_split, tune_thresholds


def test_evaluate_thresholds_split() -> None:
    items = [
        {"confidence": 0.90, "predicted": "real_bug_report", "actual": "real_bug_report", "item_type": "issue"},
        {"confidence": 0.85, "predicted": "low_effort", "actual": "low_effort", "item_type": "issue"},
        {"confidence": 0.60, "predicted": "support_question", "actual": "support_question", "item_type": "issue"},
        {"confidence": 0.40, "predicted": "real_bug_report", "actual": "feature_request", "item_type": "issue"},
    ]

    acc, cov, fr = evaluate_thresholds_split(items, high_th=0.80, medium_th=0.50)
    assert cov == 50.0  # 2 of 4 items >= 0.80
    assert acc == 1.0   # Both high items are correct
    assert fr == 0      # 0 false rejects


def test_tune_thresholds_heldout_split() -> None:
    # 10 items
    items = [
        # Train (7 items)
        {"confidence": 0.95, "predicted": "real_bug_report", "actual": "real_bug_report", "item_type": "issue"},
        {"confidence": 0.90, "predicted": "low_effort", "actual": "low_effort", "item_type": "issue"},
        {"confidence": 0.88, "predicted": "ready_for_review", "actual": "ready_for_review", "item_type": "pull_request"},
        {"confidence": 0.70, "predicted": "feature_request", "actual": "feature_request", "item_type": "issue"},
        {"confidence": 0.65, "predicted": "support_question", "actual": "support_question", "item_type": "issue"},
        {"confidence": 0.45, "predicted": "real_bug_report", "actual": "support_question", "item_type": "issue"},
        {"confidence": 0.40, "predicted": "low_effort", "actual": "feature_request", "item_type": "issue"},
        # Held-out (3 items)
        {"confidence": 0.92, "predicted": "real_bug_report", "actual": "real_bug_report", "item_type": "issue"},
        {"confidence": 0.82, "predicted": "ready_for_review", "actual": "ready_for_review", "item_type": "pull_request"},
        {"confidence": 0.55, "predicted": "support_question", "actual": "support_question", "item_type": "issue"},
    ]

    tuning = tune_thresholds(items, current_high=0.80, current_medium=0.50, train_split=0.70)

    assert tuning.recommended_high >= 0.80
    assert tuning.recommended_medium >= 0.50
    assert tuning.recommended_heldout_acc == 1.0
    assert len(tuning.candidates) > 0
