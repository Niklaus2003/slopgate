"""Unit tests for offline replay ingestion and export."""

from slopgate.ingest.replay import (
    export_gold_candidates_csv,
    load_replay_items,
    save_replay_items,
)
from slopgate.models import Item


def test_save_and_load_replay_items(tmp_path):
    dest = tmp_path / "replay.json"
    items = [
        Item(repo="pallets/flask", number=1, type="issue", title="Bug 1", body="Body 1"),
        Item(repo="pallets/flask", number=2, type="pull_request", title="Fix 1", body="Closes #1"),
    ]
    save_replay_items(items, dest)
    assert dest.is_file()

    loaded = load_replay_items(dest)
    assert len(loaded) == 2
    assert loaded[0].id == "pallets/flask#1"
    assert loaded[1].type == "pull_request"


def test_export_gold_candidates_csv(tmp_path):
    dest = tmp_path / "gold.csv"
    items = [
        Item(
            repo="pallets/flask",
            number=10,
            type="issue",
            title="Needs repro",
            body="Here is some info",
            raw={"labels": [{"name": "needs-info"}]},
        )
    ]
    count = export_gold_candidates_csv(items, dest, limit=5)
    assert count == 1
    assert dest.is_file()
    content = dest.read_text(encoding="utf-8")
    assert "pallets/flask#10" in content
    assert "needs-info" in content
