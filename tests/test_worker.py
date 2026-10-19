"""End-to-end tests for SlopGate Worker queue draining, crash recovery, and receipts.

Follows: architecture.md §3, §7, implementation-plan.md Phase 7 Exit Criteria.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slopgate.agent.tools import compute_idempotency_key
from slopgate.bedrock.budget import BudgetGuard
from slopgate.bedrock.client import MockBedrockClient
from slopgate.config import load_policy
from slopgate.decider.client import FakeDecider
from slopgate.ingest.replay import load_replay_items
from slopgate.models import ActionKind, DeciderResult, Item
from slopgate.policy.gate import ConfidenceGate
from slopgate.report.receipts import build_item_receipt
from slopgate.report.summary import RunSummary
from slopgate.state.repo_index import RepoIndex
from slopgate.store.db import (
    count_items_by_status,
    get_actions_for_item,
    get_all_item_ids,
    init_db,
    save_action,
    save_item,
    update_item_status,
)
from slopgate.worker import Worker, plan_item_actions

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"


@pytest.fixture
def policy():
    return load_policy()


@pytest.fixture
def repo_index():
    tree_path = SAMPLES_DIR / "flask_tree.json"
    if tree_path.is_file():
        files = json.loads(tree_path.read_text(encoding="utf-8"))
        return RepoIndex.from_file_list(files)
    return RepoIndex.from_file_list(["src/flask/app.py", "src/flask/blueprints.py"])


def test_plan_item_actions_routine_bug(policy):
    """Verify plan_item_actions routes confident bug report to apply_label."""
    item = Item(
        repo="pallets/flask",
        number=10,
        type="issue",
        title="Valid bug report",
        body="repro code",
        created_at="2026-10-18T10:00:00Z",
    )
    results = [
        DeciderResult(
            question_id="Q1",
            qtype="choice",
            answer="real_bug_report",
            probs={"real_bug_report": 0.95, "other": 0.05},
            confidence=0.90,
        )
    ]
    gate = ConfidenceGate()
    plan = plan_item_actions(item, results, policy, gate)

    assert plan.overall == ActionKind.PROCEED
    assert len(plan.steps) == 1
    assert plan.steps[0].tool_name == "apply_label"
    assert plan.steps[0].args["label"] == policy.labels.get("triaged", "triaged")


def test_plan_item_actions_support_question(policy):
    """Verify plan_item_actions routes support question to comment and label."""
    item = Item(
        repo="pallets/flask",
        number=11,
        type="issue",
        title="How to configure session cookie?",
        body="Where is the documentation for cookies?",
        created_at="2026-10-18T10:00:00Z",
    )
    results = [
        DeciderResult(
            question_id="Q1",
            qtype="choice",
            answer="support_question",
            probs={"support_question": 0.90, "other": 0.10},
            confidence=0.80,
        )
    ]
    gate = ConfidenceGate()
    plan = plan_item_actions(item, results, policy, gate)

    assert plan.overall == ActionKind.PROCEED
    tools = [s.tool_name for s in plan.steps]
    assert "apply_label" in tools
    assert "post_comment" in tools


def test_plan_item_actions_security_report_invariant(policy):
    """Verify security report is gated to CONFIRM as a hard invariant."""
    item = Item(
        repo="pallets/flask",
        number=12,
        type="issue",
        title="Vulnerability report in header parsing",
        body="RCE exploit vector found.",
        created_at="2026-10-18T10:00:00Z",
    )
    results = [
        DeciderResult(
            question_id="Q1",
            qtype="choice",
            answer="security_report",
            probs={"security_report": 0.99, "other": 0.01},
            confidence=0.98,
        )
    ]
    gate = ConfidenceGate()
    plan = plan_item_actions(item, results, policy, gate)

    # Hard invariant: security report is NEVER proceed
    assert plan.overall == ActionKind.CONFIRM
    assert any(s.tool_name == "flag_for_maintainer" for s in plan.steps)


def test_worker_crash_recovery_and_idempotency(tmp_path, policy, repo_index):
    """Verify crash recovery resets stale 'processing' items, and rerun avoids duplicate actions."""
    db_file = tmp_path / "crash_test.db"
    conn = init_db(db_file)

    item1 = Item(
        repo="pallets/flask",
        number=101,
        type="issue",
        title="First issue crashed mid-run",
        body="Content",
        created_at="2026-10-18T10:00:00Z",
    )
    item_id1 = save_item(conn, item1)

    # Simulate crash mid-run: status left in 'processing', but action already recorded
    update_item_status(conn, item_id1, "processing")
    save_action(
        conn=conn,
        item_id=item_id1,
        tool="apply_label",
        args={"label": "triaged"},
        handler_result="proceed",
        dry_run=True,
        idempotency_key=compute_idempotency_key("apply_label", "pallets/flask", 101, {"label": "triaged"}),
    )

    item2 = Item(
        repo="pallets/flask",
        number=102,
        type="issue",
        title="Second queued issue",
        body="Content",
        created_at="2026-10-18T10:00:00Z",
    )
    save_item(conn, item2)

    # Verify initial database status
    counts = count_items_by_status(conn)
    assert counts.get("processing") == 1
    assert counts.get("queued") == 1

    # Worker initializes and runs
    decider = FakeDecider()
    worker = Worker(
        conn=conn,
        policy=policy,
        decider=decider,
        bedrock_client=MockBedrockClient(),
        repo_index=repo_index,
        dry_run=True,
    )

    summary = worker.run()

    # Both items should be processed
    assert summary.total_items == 2
    counts_after = count_items_by_status(conn)
    assert counts_after.get("queued", 0) == 0
    assert counts_after.get("processing", 0) == 0

    # Verify idempotency key prevented duplicate 'apply_label' action insertion for item 101
    actions_item1 = get_actions_for_item(conn, item_id1)
    label_actions = [a for a in actions_item1 if a["tool"] == "apply_label"]
    assert len(label_actions) == 1  # No duplicate action recorded

    conn.close()


def test_worker_drains_queue_end_to_end_20_items(tmp_path, policy, repo_index):
    """CRITICAL PHASE 7 EXIT CRITERION:

    `slopgate run` drains a queue of >= 20 real replayed items end to end.
    A receipt exists for every item and matches actions taken.
    Run summary prints accurate counts and timings.
    """
    samples_path = SAMPLES_DIR / "flask.json"
    if not samples_path.is_file():
        pytest.skip("Replay sample file flask.json not found")

    items = load_replay_items(samples_path)[:20]
    assert len(items) >= 20, "Expected at least 20 items in replay sample"

    db_file = tmp_path / "worker_e2e_20.db"
    conn = init_db(db_file)

    # 1. Enqueue 20 real replayed items
    for it in items:
        save_item(conn, it)

    initial_counts = count_items_by_status(conn)
    assert initial_counts["queued"] == 20

    # 2. Run Worker with FakeDecider and MockBedrockClient
    decider = FakeDecider()
    budget = BudgetGuard(max_calls=50)
    worker = Worker(
        conn=conn,
        policy=policy,
        decider=decider,
        bedrock_client=MockBedrockClient(),
        budget=budget,
        repo_index=repo_index,
        dry_run=True,
    )

    summary = worker.run()

    # 3. Verify queue is completely drained
    final_counts = count_items_by_status(conn)
    assert final_counts.get("queued", 0) == 0
    assert final_counts.get("processing", 0) == 0

    # 4. Verify run summary accurately matches processed counts
    assert isinstance(summary, RunSummary)
    assert summary.total_items == 20
    assert summary.executed + summary.pending_approval + summary.flagged == 20
    assert summary.errors == 0
    assert summary.total_decisions >= 20
    assert summary.duration_seconds > 0.0

    # 5. Verify receipt exists for every item and matches stored actions
    all_ids = get_all_item_ids(conn)
    assert len(all_ids) == 20

    for item_id in all_ids:
        receipt = build_item_receipt(conn, item_id)
        assert receipt["receipt_version"] == 1
        assert receipt["item"]["id"] == item_id
        assert receipt["summary"]["status"] in ("executed", "pending_approval", "flagged")

        stored_actions = get_actions_for_item(conn, item_id)
        assert receipt["summary"]["actions_recorded"] == len(stored_actions)

    conn.close()
