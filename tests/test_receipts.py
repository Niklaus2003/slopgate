"""Unit tests for receipt generation, Markdown rendering, and disk export."""

from __future__ import annotations

import json

import pytest

from slopgate.models import DeciderResult, GateVerdict, Item
from slopgate.report.receipts import (
    build_item_receipt,
    export_receipt_to_disk,
    render_markdown_receipt,
)
from slopgate.store.db import (
    init_db,
    save_action,
    save_decision,
    save_escalation,
    save_item,
    save_pending_approval,
)


@pytest.fixture
def populated_db(tmp_path):
    """Seed a test database with an item, decisions, actions, escalations, and approvals."""
    db_file = tmp_path / "receipt_test.db"
    conn = init_db(db_file)

    item = Item(
        repo="pallets/flask",
        number=321,
        type="issue",
        title="Custom HTTPException handling crash",
        body="Traceback on route dispatch.",
        created_at="2026-10-18T10:00:00Z",
    )
    item_id = save_item(conn, item, state_text="State preview", state_hash="hash1234567890abcdef")

    # Add decision
    dec = DeciderResult(
        question_id="Q1",
        qtype="choice",
        answer="real_bug_report",
        probs={"real_bug_report": 0.92, "other": 0.08},
        confidence=0.84,
        latency_ms=14.2,
        model_id="StrandsAgents/strands-decider-2B-hobson-v21",
        from_cache=False,
    )
    verdict = GateVerdict(
        question_id="Q1",
        band="high",
        action="proceed",
        reason="Confirmed bug report with reproduction.",
    )
    save_decision(conn, item_id, dec, verdict=verdict, question_text_hash="qhash", state_hash="hash1234567890abcdef")

    # Add action
    save_action(
        conn=conn,
        item_id=item_id,
        tool="apply_label",
        args={"label": "triaged"},
        handler_result="proceed",
        dry_run=True,
        idempotency_key="pallets/flask#321:apply_label:triaged",
    )

    # Add escalation
    save_escalation(
        conn=conn,
        item_id=item_id,
        purpose="draft_reply",
        bedrock_model="amazon.nova-micro-v1:0",
        tokens_in=150,
        tokens_out=40,
        latency_ms=120.0,
        est_cost_usd=0.00001,
        output_text="Please provide a minimal reproducible script.",
    )

    # Add pending approval
    save_pending_approval(
        conn=conn,
        item_id=item_id,
        proposed_plan={"steps": [{"tool_name": "apply_label", "args": {"label": "triaged"}}]},
        receipt_md="Triage confirmation",
    )

    yield conn, item_id
    conn.close()


def test_build_item_receipt_structure(populated_db):
    """Verify build_item_receipt compiles complete and accurate metrics."""
    conn, item_id = populated_db

    receipt = build_item_receipt(conn, item_id)

    assert receipt["receipt_version"] == 1
    assert receipt["item"]["id"] == item_id
    assert receipt["item"]["repo"] == "pallets/flask"
    assert receipt["item"]["number"] == 321
    assert receipt["item"]["state_hash"] == "hash1234567890abcdef"

    summary = receipt["summary"]
    assert summary["overall_band"] == "high"
    assert summary["overall_action"] == "proceed"
    assert summary["total_decisions"] == 1
    assert summary["total_decider_latency_ms"] == 14.2
    assert summary["total_bedrock_cost_usd"] > 0
    assert summary["actions_recorded"] == 1
    assert summary["pending_approvals_count"] == 1

    assert len(receipt["decisions"]) == 1
    assert len(receipt["actions"]) == 1
    assert len(receipt["escalations"]) == 1


def test_render_markdown_receipt(populated_db):
    """Verify Markdown receipt formatting contains headers, tables, and badge details."""
    conn, item_id = populated_db
    receipt = build_item_receipt(conn, item_id)

    md = render_markdown_receipt(receipt)

    assert "# SlopGate Triage Receipt: pallets/flask#321" in md
    assert "> **Status:**" in md
    assert "Custom HTTPException handling crash" in md
    assert "## 🧠 Model Inferences & Safety Verdicts" in md
    assert "real_bug_report" in md
    assert "## ⚡ Actions & Audit Trail" in md
    assert "apply_label" in md
    assert "## ☁️ Amazon Bedrock Escalations" in md
    assert "amazon.nova-micro-v1:0" in md
    assert "## 👤 Maintainer Review Status" in md


def test_export_receipt_to_disk(populated_db, tmp_path):
    """Verify exporting receipts to disk as Markdown and JSON files."""
    conn, item_id = populated_db
    receipt = build_item_receipt(conn, item_id)

    out_dir = tmp_path / "receipts_export"

    # Export markdown
    md_path = export_receipt_to_disk(receipt, output_dir=out_dir, as_markdown=True)
    assert md_path.is_file()
    assert md_path.suffix == ".md"
    content_md = md_path.read_text(encoding="utf-8")
    assert "SlopGate Triage Receipt" in content_md

    # Export json
    json_path = export_receipt_to_disk(receipt, output_dir=out_dir, as_markdown=False)
    assert json_path.is_file()
    assert json_path.suffix == ".json"
    content_json = json.loads(json_path.read_text(encoding="utf-8"))
    assert content_json["receipt_version"] == 1
    assert content_json["item"]["number"] == 321
