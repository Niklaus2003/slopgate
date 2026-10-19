"""Unit tests for ScriptedExecutor routine plan execution and safety gating."""

from __future__ import annotations

import sqlite3

import pytest

from slopgate.agent.executor import ScriptedExecutor
from slopgate.config import load_policy
from slopgate.models import ActionKind, ActionPlan, DeciderResult, Item, PlannedToolCall
from slopgate.policy.gate import ConfidenceGate
from slopgate.store.db import get_pending_approvals, init_db, save_item


@pytest.fixture
def db_conn():
    conn = init_db(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def policy():
    return load_policy()


@pytest.fixture
def gate():
    return ConfidenceGate()


@pytest.fixture
def executor(gate, policy):
    return ScriptedExecutor(gate=gate, policy=policy)


@pytest.fixture
def sample_item(db_conn: sqlite3.Connection) -> tuple[Item, int]:
    item = Item(
        repo="pallets/flask",
        number=202,
        type="issue",
        title="Valid crash report",
        body="Detailed traceback with minimal repro code",
        created_at="2026-10-15T12:00:00Z",
    )
    item_id = save_item(db_conn, item)
    return item, item_id


def test_executor_runs_routine_plan_dry_run(
    executor: ScriptedExecutor, db_conn: sqlite3.Connection, sample_item: tuple[Item, int]
):
    item, item_id = sample_item
    results = [
        DeciderResult(
            question_id="Q1",
            qtype="choice",
            answer="real_bug_report",
            probs={"real_bug_report": 0.95, "other": 0.05},
            confidence=0.90,
        )
    ]

    plan = ActionPlan(
        steps=[
            PlannedToolCall(tool_name="apply_label", args={"label": "triage:bug"}),
            PlannedToolCall(
                tool_name="post_comment",
                args={"body": "Thank you for the report! We will investigate."},
            ),
        ],
        overall=ActionKind.PROCEED,
        receipt_notes=["Classified real_bug_report with 0.90 confidence"],
    )

    report = executor.execute_plan(
        item=item,
        plan=plan,
        results=results,
        conn=db_conn,
        item_id=item_id,
        dry_run=True,
    )

    assert report.overall_status == "executed"
    assert len(report.steps) == 2
    assert report.steps[0].status == "simulated"
    assert report.steps[1].status == "simulated"

    # Verify actions were recorded in database
    actions = db_conn.execute("SELECT * FROM actions WHERE item_id = ?", (item_id,)).fetchall()
    assert len(actions) == 2

    # Verify item status was updated to 'executed'
    item_row = db_conn.execute("SELECT status FROM items WHERE id = ?", (item_id,)).fetchone()
    assert item_row["status"] == "executed"


def test_close_item_provably_diverts_to_pending_approval(
    executor: ScriptedExecutor, db_conn: sqlite3.Connection, sample_item: tuple[Item, int]
):
    """CRITICAL SAFETY INVARIANT TEST:

    A plan attempting to close an issue MUST NEVER auto-execute.
    The executor must halt and save the plan to pending_approvals.
    """
    item, item_id = sample_item
    results = [
        DeciderResult(
            question_id="Q1",
            qtype="choice",
            answer="low_effort",
            probs={"low_effort": 0.98},
            confidence=0.96,
        )
    ]

    plan = ActionPlan(
        steps=[
            PlannedToolCall(tool_name="apply_label", args={"label": "low-effort"}),
            PlannedToolCall(tool_name="close_item", args={"reason": "Incomplete submission"}),
        ],
        overall=ActionKind.CONFIRM,
    )

    report = executor.execute_plan(
        item=item,
        plan=plan,
        results=results,
        conn=db_conn,
        item_id=item_id,
        dry_run=True,
    )

    # Step 1 (apply_label) executed
    assert report.steps[0].tool_name == "apply_label"
    assert report.steps[0].status == "simulated"

    # Step 2 (close_item) diverted to pending_approval
    assert report.steps[1].tool_name == "close_item"
    assert report.steps[1].status == "pending_approval"
    assert report.overall_status == "pending_approval"
    assert report.pending_approval_id is not None

    # Check pending_approvals table
    pending = get_pending_approvals(db_conn, status="pending")
    assert len(pending) == 1
    assert pending[0]["item_id"] == item_id
    assert "close_item" in pending[0]["proposed_plan_json"]

    # Verify item status is 'pending_approval'
    item_row = db_conn.execute("SELECT status FROM items WHERE id = ?", (item_id,)).fetchone()
    assert item_row["status"] == "pending_approval"

    # Verify close_item was NEVER executed in actions table
    close_action = db_conn.execute("SELECT * FROM actions WHERE tool = 'close_item'").fetchone()
    assert close_action is None


def test_executor_idempotency_on_repeated_runs(
    executor: ScriptedExecutor, db_conn: sqlite3.Connection, sample_item: tuple[Item, int]
):
    item, item_id = sample_item
    results = [
        DeciderResult(
            question_id="Q1",
            qtype="choice",
            answer="real_bug_report",
            probs={"real_bug_report": 0.95},
            confidence=0.90,
        )
    ]

    plan = ActionPlan(
        steps=[PlannedToolCall(tool_name="apply_label", args={"label": "bug"})],
        overall=ActionKind.PROCEED,
    )

    # Run 1
    rep1 = executor.execute_plan(item, plan, results, db_conn, item_id, dry_run=True)
    assert rep1.steps[0].status == "simulated"

    # Run 2 with same plan
    rep2 = executor.execute_plan(item, plan, results, db_conn, item_id, dry_run=True)
    assert rep2.steps[0].status == "skipped"

    # Actions table still has only 1 row
    rows = db_conn.execute("SELECT * FROM actions WHERE item_id = ?", (item_id,)).fetchall()
    assert len(rows) == 1


def test_executor_handles_deny(
    executor: ScriptedExecutor, db_conn: sqlite3.Connection, sample_item: tuple[Item, int]
):
    item, item_id = sample_item
    # Missing required decision Q1 causes DENY or CONFIRM depending on gate
    results: list[DeciderResult] = []

    plan = ActionPlan(
        steps=[PlannedToolCall(tool_name="apply_label", args={"label": "bug"})],
        overall=ActionKind.CONFIRM,
    )

    report = executor.execute_plan(item, plan, results, db_conn, item_id, dry_run=True)
    assert report.overall_status in ("pending_approval", "denied")


def test_executor_handles_tool_error(
    executor: ScriptedExecutor, db_conn: sqlite3.Connection, sample_item: tuple[Item, int]
):
    item, item_id = sample_item
    results = [
        DeciderResult(
            question_id="Q1",
            qtype="choice",
            answer="real_bug_report",
            probs={"real_bug_report": 0.95},
            confidence=0.90,
        )
    ]

    # Tool call missing required argument 'label' raises KeyError in _execute_single_tool
    plan = ActionPlan(
        steps=[PlannedToolCall(tool_name="apply_label", args={})],
        overall=ActionKind.PROCEED,
    )

    report = executor.execute_plan(item, plan, results, db_conn, item_id, dry_run=True)
    assert report.overall_status == "error"
    assert report.steps[0].status == "error"

    # Verify item status was updated to 'error'
    item_row = db_conn.execute("SELECT status FROM items WHERE id = ?", (item_id,)).fetchone()
    assert item_row["status"] == "error"
