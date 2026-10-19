"""Offline backtesting and Bedrock-only baseline comparisons."""

from slopgate.backtest.baseline import BaselineResult, run_bedrock_baseline
from slopgate.backtest.proxy import (
    load_gold_labels_from_csv,
    map_item_to_proxy_label,
    populate_proxy_ground_truth,
)
from slopgate.backtest.runner import BacktestResult, run_backtest
from slopgate.backtest.tuning import TuningComparison, tune_thresholds

__all__ = [
    "BacktestResult",
    "BaselineResult",
    "TuningComparison",
    "load_gold_labels_from_csv",
    "map_item_to_proxy_label",
    "populate_proxy_ground_truth",
    "run_backtest",
    "run_bedrock_baseline",
    "tune_thresholds",
]
