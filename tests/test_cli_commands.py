"""CLI integration tests for slopgate run, report, and demo commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slopgate.cli import main
from slopgate.ingest.replay import load_replay_items
from slopgate.store.db import init_db, save_item

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"


@pytest.fixture
def test_env(tmp_path):
    """Seed test database with 5 sample items."""
    db_file = tmp_path / "cli_test.db"
    conn = init_db(db_file)

    samples_path = SAMPLES_DIR / "flask.json"
    if not samples_path.is_file():
        pytest.skip("Replay sample file flask.json not found")

    items = load_replay_items(samples_path)[:5]
    for it in items:
        save_item(conn, it)
    conn.close()

    return str(db_file), str(SAMPLES_DIR / "flask_tree.json")


def test_cli_run_command(test_env, capsys):
    """Verify 'slopgate run' executes worker and outputs run summary."""
    db_path, tree_path = test_env

    ret = main([
        "run",
        "--limit", "3",
        "--db", db_path,
        "--tree", tree_path,
        "--decider", "fake",
        "--mock-bedrock",
    ])
    assert ret == 0

    captured = capsys.readouterr().out
    assert "SlopGate Background Triage Worker" in captured
    assert "SlopGate Worker Run Summary" in captured
    assert "Items Processed:      3" in captured


def test_cli_report_command(test_env, capsys, tmp_path):
    """Verify 'slopgate report' generates single item receipt and exports all."""
    db_path, _ = test_env

    # First run worker to process items
    main([
        "run",
        "--limit", "2",
        "--db", db_path,
        "--decider", "fake",
        "--mock-bedrock",
    ])
    capsys.readouterr()  # clear buffer

    # Single item receipt markdown output
    ret = main(["report", "--item", "1", "--db", db_path])
    assert ret == 0
    captured = capsys.readouterr().out
    assert "# SlopGate Triage Receipt" in captured
    assert "pallets/flask" in captured

    # Single item receipt json output
    ret_json = main(["report", "--item", "1", "--db", db_path, "--json"])
    assert ret_json == 0
    captured_json = capsys.readouterr().out
    parsed = json.loads(captured_json)
    assert parsed["receipt_version"] == 1
    assert parsed["item"]["id"] == 1

    # Export all receipts to directory
    out_dir = tmp_path / "exported_receipts"
    ret_all = main(["report", "--all", "--db", db_path, "--output", str(out_dir)])
    assert ret_all == 0
    assert out_dir.is_dir()
    exported_files = list(out_dir.glob("*.md"))
    assert len(exported_files) >= 2


def test_cli_demo_command(tmp_path, capsys):
    """Verify 'slopgate demo' runs end-to-end showcase without errors."""
    demo_db = tmp_path / "demo_showcase.db"

    ret = main(["demo", "--limit", "2", "--db", str(demo_db)])
    assert ret == 0

    captured = capsys.readouterr().out
    assert "SlopGate End-to-End Showcase Demo" in captured
    assert "[1/3] Seeded" in captured
    assert "[2/3] Running triage worker" in captured
    assert "SlopGate Worker Run Summary" in captured
    assert "[3/3] Exported demo receipts" in captured
