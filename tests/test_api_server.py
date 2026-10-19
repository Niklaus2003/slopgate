"""Unit and integration tests for FastAPI REST API server (Phase 10)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from slopgate.api.server import create_app
from slopgate.models import Item
from slopgate.store.db import init_db, save_item, save_pending_approval


def test_api_health_and_doctor():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = str(Path(tmp_dir) / "test.db")
        app = create_app(db_path=db_path)
        client = TestClient(app)

        # Health
        res = client.get("/api/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert "version" in data

        # Doctor
        res = client.get("/api/doctor")
        assert res.status_code == 200
        data = res.json()
        assert "python_version" in data
        assert data["torch_device"] == "cpu"


def test_api_demo_fixtures():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = str(Path(tmp_dir) / "test.db")
        app = create_app(db_path=db_path)
        client = TestClient(app)

        res = client.get("/api/demo/fixtures")
        assert res.status_code == 200
        fixtures = res.json()
        assert len(fixtures) == 6
        assert fixtures[0]["id"] == "clean-bug"
        assert fixtures[0]["expected_band"] == "HIGH"
        assert fixtures[5]["id"] == "security-report"


def test_api_items_and_receipt():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = str(Path(tmp_dir) / "test.db")
        conn = init_db(db_path)

        # Insert test item
        item = Item(
            id=101,
            repo="pallets/flask",
            number=101,
            type="issue",
            title="Test Issue Title",
            body="Test Issue Body",
            state="open",
        )
        item_id = save_item(conn, item)
        conn.close()

        app = create_app(db_path=db_path)
        client = TestClient(app)

        # List items
        res = client.get("/api/items")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "Test Issue Title"

        # Receipt
        res_rcpt = client.get(f"/api/items/{item_id}/receipt")
        assert res_rcpt.status_code == 200
        rcpt_data = res_rcpt.json()
        assert "receipt" in rcpt_data
        assert "markdown" in rcpt_data
        assert "# SlopGate Triage Receipt" in rcpt_data["markdown"]


def test_api_live_triage():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = str(Path(tmp_dir) / "test.db")
        app = create_app(db_path=db_path, decider_mode="fake")
        client = TestClient(app)

        payload = {
            "title": "Bug: blueprint url_prefix error",
            "body": "### Description\nError occurs in scaffold.py\n```python\napp.register_blueprint(bp)\n```",
            "repo": "pallets/flask",
            "type": "issue",
            "decider": "fake",
            "run_bedrock": False,
        }

        res = client.post("/api/triage", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "state_hash" in data
        assert "facts" in data
        assert data["facts"]["has_code_blocks"] is True
        assert "primary_classification" in data
        assert "band" in data
        assert "verdict" in data
        assert "planned_tools" in data
        assert data["latency_ms"] >= 0.0


def test_api_approvals_and_action():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = str(Path(tmp_dir) / "test.db")
        conn = init_db(db_path)

        # Create item & pending approval
        item = Item(
            id=102,
            repo="pallets/flask",
            number=102,
            type="issue",
            title="Close test item",
            body="Please close",
            state="open",
        )
        item_id = save_item(conn, item)
        approval_id = save_pending_approval(
            conn,
            item_id=item_id,
            proposed_plan={"steps": [{"tool_name": "close_item", "args": {"reason": "Closed test"}}]},
            receipt_md="Receipt for #102",
        )
        conn.close()

        app = create_app(db_path=db_path)
        client = TestClient(app)

        # List pending
        res = client.get("/api/approvals?status=pending")
        assert res.status_code == 200
        apps = res.json()
        assert len(apps) == 1
        assert apps[0]["id"] == approval_id

        # Action: Approve (dry-run)
        act_res = client.post(f"/api/approvals/{approval_id}/action", json={"action": "approve", "live": False})
        assert act_res.status_code == 200
        assert act_res.json()["status"] == "approved"

        # Verify no longer pending
        res_after = client.get("/api/approvals?status=pending")
        assert len(res_after.json()) == 0


def test_api_calibration_stats():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = str(Path(tmp_dir) / "test.db")
        conn = init_db(db_path)
        conn.close()

        app = create_app(db_path=db_path)
        client = TestClient(app)

        res = client.get("/api/stats/calibration")
        assert res.status_code == 200
        stats = res.json()
        assert "bands" in stats
        assert "economics" in stats
        assert stats["unattended_closes"] == 0
        assert "performance" in stats
        assert "hardware" in stats
