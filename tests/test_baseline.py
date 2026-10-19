"""Unit tests for Bedrock classification baseline runner."""

from __future__ import annotations

from pathlib import Path

from slopgate.backtest.baseline import run_bedrock_baseline
from slopgate.bedrock.budget import BudgetGuard
from slopgate.bedrock.client import MockBedrockClient
from slopgate.models import Item
from slopgate.store.db import get_escalations_by_purpose, init_db, save_ground_truth, save_item


def test_bedrock_baseline_execution(tmp_path: Path) -> None:
    db_file = tmp_path / "baseline_test.db"
    conn = init_db(db_file)

    items = [
        Item(repo="pallets/flask", number=1, type="issue", title="Real bug", body="Bug details"),
        Item(repo="pallets/flask", number=2, type="pull_request", title="Typo fix", body="Typo"),
    ]
    for item in items:
        item_id = save_item(conn, item)
        save_ground_truth(conn, item_id, "real_bug_report" if item.type == "issue" else "ready_for_review")

    client = MockBedrockClient(
        canned_json={"label": "real_bug_report", "reason": "Accurate bug report."}
    )
    budget = BudgetGuard(max_calls=10, max_cost_usd=1.0)

    res = run_bedrock_baseline(items, conn, client, budget, limit=2)

    assert res.total_items == 2
    assert res.total_tokens_in > 0
    assert res.total_tokens_out > 0
    assert res.total_cost_usd > 0.0
    assert len(res.latencies_ms) == 2

    # Verify escalations recorded in database
    esc_rows = get_escalations_by_purpose(conn, purpose="baseline")
    assert len(esc_rows) == 2
    assert esc_rows[0]["purpose"] == "baseline"

    conn.close()


def test_bedrock_baseline_budget_exhaustion(tmp_path: Path) -> None:
    db_file = tmp_path / "budget_test.db"
    conn = init_db(db_file)

    items = [Item(repo="test/repo", number=i, type="issue", title=f"Issue {i}", body="Body") for i in range(5)]
    client = MockBedrockClient(canned_json={"label": "low_effort", "reason": "No details."})
    # Budget limited to 2 calls
    budget = BudgetGuard(max_calls=2, max_cost_usd=1.0)

    res = run_bedrock_baseline(items, conn, client, budget, limit=5)

    assert res.total_items == 2
    conn.close()
