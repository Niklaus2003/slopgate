"""Golden test for deterministic offline backtest execution.

Verifies that fixed replay data with FakeDecider generates exact,
reproducible calibration metrics, zero false-reject rate, and zero live mutations.
Follows: implementation-plan.md Phase 8 Step 8, architecture.md §7.3.
"""

from __future__ import annotations

from pathlib import Path

from slopgate.backtest.proxy import populate_proxy_ground_truth
from slopgate.backtest.runner import run_backtest
from slopgate.config import load_policy
from slopgate.decider.client import FakeDecider
from slopgate.ingest.replay import load_replay_items
from slopgate.report.calibration import (
    compute_calibration_metrics,
    render_markdown_calibration_report,
)
from slopgate.state.repo_index import RepoIndex
from slopgate.store.db import get_actions_for_item, get_all_item_ids, init_db

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"


def test_golden_offline_backtest(tmp_path: Path) -> None:
    db_file = tmp_path / "golden_backtest.db"
    conn = init_db(db_file)
    policy = load_policy()

    sample_file = SAMPLES_DIR / "flask.json"
    tree_file = SAMPLES_DIR / "flask_tree.json"
    assert sample_file.is_file(), f"Sample dataset missing at {sample_file}"

    # 1. Load exactly 20 items
    all_items = load_replay_items(sample_file)
    items = all_items[:20]
    assert len(items) == 20

    # 2. Populate proxy ground truth
    populated = populate_proxy_ground_truth(conn, items)
    assert populated == 20

    # 3. Setup repo index and fake decider
    repo_index = RepoIndex.from_json(tree_file) if tree_file.is_file() else None
    decider = FakeDecider()

    # 4. Run backtest
    result = run_backtest(
        items=items,
        conn=conn,
        policy=policy,
        decider=decider,
        repo_index=repo_index,
    )

    # 5. Deterministic invariant assertions
    assert result.total_items == 20
    assert result.total_decisions >= 20  # Q1 plus conditional follow-ups
    assert len(result.items_summary) == 20

    # CRITICAL SAFETY INVARIANT: Backtest must NEVER execute actions or write to actions table
    item_ids = get_all_item_ids(conn)
    for i_id in item_ids:
        actions = get_actions_for_item(conn, i_id)
        assert len(actions) == 0, f"Backtest wrote actions for item_id {i_id}!"

    # 6. Compute calibration metrics
    metrics = compute_calibration_metrics(conn)
    assert metrics.total_evaluated == 20
    assert metrics.proxy_count == 20
    assert metrics.false_reject_count == 0
    assert metrics.false_reject_rate_pct == 0.0
    assert metrics.decider_p50_latency_ms >= 0.0

    # 7. Render report and check essential sections
    report_md = render_markdown_calibration_report(metrics)
    assert "# SlopGate — Model Calibration & Safety Backtest Report" in report_md
    assert "False-Reject Rate on Accepted PRs/Issues" in report_md
    assert "0.0%" in report_md
    assert "HARD-GATED" in report_md

    conn.close()
