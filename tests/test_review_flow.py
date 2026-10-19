"""Unit and CLI integration tests for maintainer review flow (approve/reject).

Follows: architecture.md §6.6, §7.3, problem-statement.md §9.
"""

from __future__ import annotations

import pytest

from slopgate.cli import execute_approved_plan, main
from slopgate.models import Item
from slopgate.store.db import (
    get_audit_log,
    get_item_by_id,
    get_pending_approval_by_id,
    init_db,
    save_item,
    save_pending_approval,
)


@pytest.fixture
def review_setup(tmp_path):
    """Set up a database with a pending close_item approval."""
    db_file = tmp_path / "review_test.db"
    conn = init_db(db_file)

    item = Item(
        repo="pallets/flask",
        number=555,
        type="issue",
        title="Spam or empty submission",
        body="asdfghjk",
        created_at="2026-10-18T10:00:00Z",
    )
    item_id = save_item(conn, item)

    plan = {
        "status": "pending_approval",
        "steps": [
            {
                "tool_name": "apply_label",
                "args": {"label": "invalid"},
            },
            {
                "tool_name": "close_item",
                "args": {"reason": "Empty report with no actionable details."},
            },
        ],
    }

    approval_id = save_pending_approval(
        conn=conn,
        item_id=item_id,
        proposed_plan=plan,
        receipt_md="### Maintainer Review Required\nAutomated closure proposed due to empty body.",
    )

    conn.close()
    return str(db_file), approval_id, item_id


def test_review_cli_list(review_setup, capsys):
    """Verify 'slopgate review list' lists pending approvals."""
    db_path, approval_id, _ = review_setup

    ret = main(["review", "list", "--db", db_path])
    assert ret == 0

    captured = capsys.readouterr().out
    assert "SlopGate Maintainer Review Inbox" in captured
    assert "Total: 1" in captured
    assert f"{approval_id}" in captured
    assert "pallets/flask#555" in captured


def test_review_cli_show(review_setup, capsys):
    """Verify 'slopgate review show <id>' displays details and proposed plan."""
    db_path, approval_id, _ = review_setup

    ret = main(["review", "show", str(approval_id), "--db", db_path])
    assert ret == 0

    captured = capsys.readouterr().out
    assert f"Approval Request ID: #{approval_id}" in captured
    assert "pallets/flask#555" in captured
    assert "Automated closure proposed" in captured
    assert "close_item" in captured


def test_review_cli_approve_executes_plan(review_setup, capsys):
    """Verify 'slopgate review approve <id>' executes the plan and updates status."""
    db_path, approval_id, item_id = review_setup

    ret = main(["review", "approve", str(approval_id), "--db", db_path])
    assert ret == 0

    captured = capsys.readouterr().out
    assert "[APPROVED] Executing action plan" in captured
    assert "Action apply_label: status=simulated" in captured
    assert "Action close_item: status=simulated" in captured
    assert "Approval executed successfully" in captured

    # Verify DB state
    conn = init_db(db_path)
    approval = get_pending_approval_by_id(conn, approval_id)
    assert approval is not None
    assert approval["status"] == "approved"

    item_row = get_item_by_id(conn, item_id)
    assert item_row is not None
    assert item_row.status == "executed"

    # Verify audit log contains close_item
    audit_entries = get_audit_log(conn, item_id)
    tool_names = [e["action"] for e in audit_entries]
    assert "apply_label" in tool_names
    assert "close_item" in tool_names
    conn.close()


def test_review_cli_reject_dismisses_plan(review_setup, capsys):
    """Verify 'slopgate review reject <id>' dismisses the plan without executing close_item."""
    db_path, approval_id, item_id = review_setup

    ret = main(["review", "reject", str(approval_id), "--db", db_path])
    assert ret == 0

    captured = capsys.readouterr().out
    assert "[REJECTED] Action plan for pallets/flask#555 has been rejected and dismissed." in captured

    # Verify DB state
    conn = init_db(db_path)
    approval = get_pending_approval_by_id(conn, approval_id)
    assert approval is not None
    assert approval["status"] == "rejected"

    item_row = get_item_by_id(conn, item_id)
    assert item_row is not None
    assert item_row.status == "dismissed"

    # Verify no audit actions were executed
    audit_entries = get_audit_log(conn, item_id)
    assert len(audit_entries) == 0
    conn.close()


def test_execute_approved_plan_dry_run_vs_live(review_setup):
    """Verify execute_approved_plan executes with dry_run safety."""
    db_path, approval_id, _item_id = review_setup
    conn = init_db(db_path)
    approval = get_pending_approval_by_id(conn, approval_id)
    assert approval is not None

    # Execute with dry_run=True (default)
    outcomes = execute_approved_plan(conn, approval, dry_run=True)
    assert len(outcomes) == 2
    assert outcomes[0]["status"] == "simulated"
    assert outcomes[1]["status"] == "simulated"
    conn.close()
