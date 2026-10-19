"""Unit tests for SQLite repository and storage operations."""

import sqlite3

from slopgate.models import ActionKind, Band, DeciderResult, GateVerdict, Item
from slopgate.store.db import (
    get_cached_decision,
    get_ground_truth,
    get_item_by_id,
    get_item_by_repo_number,
    get_pending_approvals,
    init_db,
    list_items_by_status,
    reset_stale_processing,
    save_action,
    save_decision,
    save_escalation,
    save_ground_truth,
    save_item,
    save_pending_approval,
    update_item_status,
    update_pending_approval_status,
)


def test_init_db_in_memory():
    conn = init_db(":memory:")
    assert isinstance(conn, sqlite3.Connection)
    # Check tables created
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    ]
    assert "items" in tables
    assert "decisions" in tables
    assert "actions" in tables
    assert "pending_approvals" in tables
    assert "escalations" in tables
    assert "ground_truth" in tables


def test_save_and_retrieve_item():
    conn = init_db(":memory:")
    item = Item(
        repo="pallets/flask",
        number=5000,
        type="issue",
        title="Session bug",
        body="Reproduction steps here",
        raw={"author": "alice"},
    )
    item_id = save_item(conn, item, state_text="state_str", state_hash="hash_123")
    assert item_id > 0

    fetched = get_item_by_id(conn, item_id)
    assert fetched is not None
    assert fetched.repo == "pallets/flask"
    assert fetched.number == 5000
    assert fetched.title == "Session bug"
    assert fetched.raw["author"] == "alice"

    # Test get_item_by_repo_number
    res = get_item_by_repo_number(conn, "pallets/flask", 5000)
    assert res is not None
    f_id, f_item = res
    assert f_id == item_id
    assert f_item.title == "Session bug"


def test_update_and_list_status():
    conn = init_db(":memory:")
    item1 = Item(repo="owner/repo", number=1, type="issue", title="Item 1")
    item2 = Item(repo="owner/repo", number=2, type="issue", title="Item 2")
    id1 = save_item(conn, item1)
    id2 = save_item(conn, item2)

    update_item_status(conn, id1, "decided")
    update_item_status(conn, id2, "queued")

    queued = list_items_by_status(conn, "queued")
    decided = list_items_by_status(conn, "decided")

    assert len(queued) == 1
    assert queued[0]["number"] == 2
    assert len(decided) == 1
    assert decided[0]["number"] == 1


def test_decisions_caching():
    conn = init_db(":memory:")
    item = Item(repo="owner/repo", number=10, type="issue")
    item_id = save_item(conn, item)

    decision = DeciderResult(
        question_id="Q1",
        qtype="choice",
        answer="real_bug_report",
        probs={"real_bug_report": 0.92, "low_effort": 0.08},
        confidence=0.88,
        latency_ms=15.2,
        model_id="test-decider-2b",
    )
    verdict = GateVerdict(
        question_id="Q1",
        band=Band.HIGH,
        action=ActionKind.PROCEED,
        reason="Confirmed bug",
    )

    save_decision(conn, item_id, decision, verdict, question_text_hash="q1_hash_xyz")

    cached = get_cached_decision(
        conn,
        question_id="Q1",
        question_text_hash="q1_hash_xyz",
        model_id="test-decider-2b",
    )
    assert cached is not None
    assert cached.answer == "real_bug_report"
    assert cached.confidence == 0.88
    assert cached.from_cache is True


def test_action_idempotency():
    conn = init_db(":memory:")
    item = Item(repo="owner/repo", number=15, type="issue")
    item_id = save_item(conn, item)

    # First execution succeeds
    saved_first = save_action(
        conn,
        item_id=item_id,
        tool="apply_label",
        args={"label": "triaged"},
        handler_result="proceed",
        dry_run=True,
        idempotency_key="repo#15:label:triaged",
    )
    assert saved_first is True

    # Duplicate execution with same idempotency key is safely ignored
    saved_duplicate = save_action(
        conn,
        item_id=item_id,
        tool="apply_label",
        args={"label": "triaged"},
        handler_result="proceed",
        dry_run=True,
        idempotency_key="repo#15:label:triaged",
    )
    assert saved_duplicate is False


def test_pending_approvals_and_escalations():
    conn = init_db(":memory:")
    item = Item(repo="owner/repo", number=20, type="issue", title="Ambiguous report")
    item_id = save_item(conn, item)

    approval_id = save_pending_approval(
        conn,
        item_id=item_id,
        proposed_plan={"tool": "close_item", "reason": "Requires human sign-off"},
        receipt_md="### Receipt\nClose proposed.",
    )
    assert approval_id > 0

    pending = get_pending_approvals(conn, "pending")
    assert len(pending) == 1
    assert pending[0]["title"] == "Ambiguous report"

    update_pending_approval_status(conn, approval_id, "approved")
    pending_after = get_pending_approvals(conn, "pending")
    assert len(pending_after) == 0

    # Escalations
    esc_id = save_escalation(
        conn,
        item_id=item_id,
        purpose="draft_reply",
        bedrock_model="amazon.nova-micro-v1:0",
        tokens_in=250,
        tokens_out=45,
        latency_ms=320.0,
        est_cost_usd=0.000015,
        output_text="Please provide a minimal reproduction script.",
    )
    assert esc_id > 0


def test_ground_truth_and_crash_recovery():
    conn = init_db(":memory:")
    item = Item(repo="owner/repo", number=30, type="issue", status="processing")
    item_id = save_item(conn, item)

    save_ground_truth(conn, item_id, label="real_bug_report", source="gold")
    gt = get_ground_truth(conn, item_id)
    assert gt is not None
    assert gt["label"] == "real_bug_report"
    assert gt["source"] == "gold"

    # Crash recovery: reset stale 'processing' status back to 'queued'
    reset_count = reset_stale_processing(conn)
    assert reset_count == 1

    recovered_item = get_item_by_id(conn, item_id)
    assert recovered_item is not None
    assert recovered_item.status == "queued"
