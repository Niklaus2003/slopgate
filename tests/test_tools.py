"""Unit tests for dry-run agent tools and idempotency deduplication."""

from __future__ import annotations

import json
import sqlite3

import pytest

from slopgate.agent.tools import (
    SLOPGATE_TOOLS,
    apply_label,
    close_item,
    compute_idempotency_key,
    flag_for_maintainer,
    post_comment,
    request_info_comment,
    tool_apply_label,
)
from slopgate.models import Item
from slopgate.store.db import init_db, save_item


@pytest.fixture
def db_conn():
    conn = init_db(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def sample_item(db_conn: sqlite3.Connection) -> Item:
    item = Item(
        repo="pallets/flask",
        number=101,
        type="issue",
        title="Test Bug Report",
        body="App crashes on startup with traceback",
        created_at="2026-10-15T12:00:00Z",
    )
    item_id = save_item(db_conn, item)
    assert item_id > 0
    return item


def test_idempotency_key_deterministic():
    key1 = compute_idempotency_key("apply_label", "pallets/flask", 101, {"label": "bug"})
    key2 = compute_idempotency_key("apply_label", "PALLETS/FLASK", 101, {"label": "BUG"})
    assert key1 == key2
    assert key1 == "pallets/flask#101:label:bug"

    c_key1 = compute_idempotency_key("post_comment", "pallets/flask", 101, {"body": "Thank you!"})
    c_key2 = compute_idempotency_key("post_comment", "pallets/flask", 101, {"body": "Thank you! "})
    assert c_key1 == c_key2


def test_apply_label_dry_run_and_idempotency(db_conn: sqlite3.Connection, sample_item: Item):
    # Pass 1: Simulated execution
    res1 = apply_label(
        repo=sample_item.repo,
        number=sample_item.number,
        label="triage:bug",
        dry_run=True,
        conn=db_conn,
        item_id=1,
    )
    assert res1["status"] == "simulated"
    assert res1["dry_run"] is True
    assert "idempotency_key" in res1

    # Check database action entry
    row = db_conn.execute("SELECT * FROM actions WHERE idempotency_key = ?", (res1["idempotency_key"],)).fetchone()
    assert row is not None
    assert row["tool"] == "apply_label"
    assert row["dry_run"] == 1
    assert row["executed"] == 0

    # Pass 2: Repeated call must be skipped (idempotent)
    res2 = apply_label(
        repo=sample_item.repo,
        number=sample_item.number,
        label="triage:bug",
        dry_run=True,
        conn=db_conn,
        item_id=1,
    )
    assert res2["status"] == "skipped"
    assert "Duplicate idempotency key" in res2["reason"]


def test_post_comment_dry_run_and_idempotency(db_conn: sqlite3.Connection, sample_item: Item):
    comment_text = "Thanks for filing! A maintainer will take a look."
    res1 = post_comment(
        repo=sample_item.repo,
        number=sample_item.number,
        body=comment_text,
        dry_run=True,
        conn=db_conn,
        item_id=1,
    )
    assert res1["status"] == "simulated"
    assert res1["dry_run"] is True

    # Repeated identical comment should be skipped
    res2 = post_comment(
        repo=sample_item.repo,
        number=sample_item.number,
        body=comment_text,
        dry_run=True,
        conn=db_conn,
        item_id=1,
    )
    assert res2["status"] == "skipped"


def test_request_info_comment_templates(db_conn: sqlite3.Connection, sample_item: Item):
    res = request_info_comment(
        repo=sample_item.repo,
        number=sample_item.number,
        template_type="reproduction",
        missing_fields=["Minimal code snippet", "Python version"],
        dry_run=True,
        conn=db_conn,
        item_id=1,
    )
    assert res["status"] == "simulated"

    # Verify no accusations of AI generation or insulting language
    row = db_conn.execute("SELECT args_json FROM actions WHERE tool = 'post_comment'").fetchone()
    assert row is not None
    saved_args = json.loads(row["args_json"])
    body = saved_args["body"]
    assert "ai-generated" not in body.lower()
    assert " ai " not in f" {body.lower()} "
    assert "slop" not in body.lower()
    assert "Minimal code snippet" in body


def test_flag_for_maintainer(db_conn: sqlite3.Connection, sample_item: Item):
    res = flag_for_maintainer(
        repo=sample_item.repo,
        number=sample_item.number,
        reason="Security report detected",
        suggested_action="security_review",
        dry_run=True,
        conn=db_conn,
        item_id=1,
    )
    assert res["status"] == "flagged"
    assert res["tool"] == "flag_for_maintainer"


def test_close_item_dry_run_records_confirm(db_conn: sqlite3.Connection, sample_item: Item):
    res = close_item(
        repo=sample_item.repo,
        number=sample_item.number,
        reason="Resolved in previous release",
        dry_run=True,
        conn=db_conn,
        item_id=1,
    )
    assert res["status"] == "simulated"
    row = db_conn.execute("SELECT * FROM actions WHERE tool = 'close_item'").fetchone()
    assert row is not None
    assert row["handler_result"] == "confirm"


def test_strands_tool_wrappers():
    assert len(SLOPGATE_TOOLS) == 5
    tool_names = [t.tool_name for t in SLOPGATE_TOOLS]
    assert "apply_label" in tool_names
    assert "post_comment" in tool_names
    assert "request_info_comment" in tool_names
    assert "flag_for_maintainer" in tool_names
    assert "close_item" in tool_names

    # Test invoking wrapper directly
    out = tool_apply_label(repo="pallets/flask", number=1, label="enhancement")
    data = json.loads(out)
    assert data["status"] in ("simulated", "skipped")
    assert data["tool"] == "apply_label"
