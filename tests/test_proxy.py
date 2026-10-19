"""Unit tests for proxy label mapping and ground truth loaders."""

from __future__ import annotations

import csv
from pathlib import Path

from slopgate.backtest.proxy import (
    load_gold_labels_from_csv,
    map_item_to_proxy_label,
    populate_proxy_ground_truth,
)
from slopgate.models import Item
from slopgate.store.db import get_all_ground_truth, init_db


def test_map_issue_proxy_labels() -> None:
    # 1. Rejected AI or low effort
    item_slop = Item(
        repo="pallets/flask",
        number=1,
        type="issue",
        title="[rejected AI] broken route",
        body="x",
        raw={"labels": [{"name": "rejected AI"}], "state_reason": "not_planned"},
    )
    assert map_item_to_proxy_label(item_slop) == "low_effort"

    # 2. Security report
    item_sec = Item(
        repo="pallets/flask",
        number=2,
        type="issue",
        title="Possible CVE vulnerability in cookies",
        body="Details",
        raw={"labels": [{"name": "security"}]},
    )
    assert map_item_to_proxy_label(item_sec) == "security_report"

    # 3. Duplicate
    item_dup = Item(
        repo="pallets/flask",
        number=3,
        type="issue",
        title="Server crash",
        body="This is a duplicate of #1234",
        raw={"labels": []},
    )
    assert map_item_to_proxy_label(item_dup) == "likely_duplicate"

    # 4. Support question
    item_q = Item(
        repo="pallets/flask",
        number=4,
        type="issue",
        title="How do I configure SSL in development?",
        body="Please help me",
        raw={"labels": [{"name": "question"}]},
    )
    assert map_item_to_proxy_label(item_q) == "support_question"

    # 5. Feature request
    item_feat = Item(
        repo="pallets/flask",
        number=5,
        type="issue",
        title="Add support for ASGI natively",
        body="Feature proposal",
        raw={"labels": [{"name": "enhancement"}]},
    )
    assert map_item_to_proxy_label(item_feat) == "feature_request"

    # 6. Real bug report
    item_bug = Item(
        repo="pallets/flask",
        number=6,
        type="issue",
        title="Url building fails with custom scheme",
        body="Reproducible traceback follows...",
        raw={"labels": [{"name": "bug"}], "state_reason": "completed"},
    )
    assert map_item_to_proxy_label(item_bug) == "real_bug_report"


def test_map_pr_proxy_labels() -> None:
    # 1. Merged PR -> ready_for_review
    pr_merged = Item(
        repo="pallets/flask",
        number=10,
        type="pull_request",
        title="Fix typo in docs",
        body="Fixes small typo",
        raw={"pull_request": {"merged_at": "2026-01-01T00:00:00Z"}},
    )
    assert map_item_to_proxy_label(pr_merged) == "ready_for_review"

    # 2. Rejected AI PR -> low_effort
    pr_ai = Item(
        repo="pallets/flask",
        number=11,
        type="pull_request",
        title="AI junk: rewrite wsgi router",
        body="Automated PR",
        raw={"labels": [{"name": "rejected AI"}]},
    )
    assert map_item_to_proxy_label(pr_ai) == "low_effort"

    # 3. Unmerged closed PR -> out_of_scope
    pr_closed = Item(
        repo="pallets/flask",
        number=12,
        type="pull_request",
        title="Add mongodb orm backend",
        body="Major feature addition",
        raw={"pull_request": {"merged_at": None}, "state_reason": "not_planned"},
    )
    assert map_item_to_proxy_label(pr_closed) == "out_of_scope"


def test_populate_and_load_ground_truth(tmp_path: Path) -> None:
    db_file = tmp_path / "gt_test.db"
    conn = init_db(db_file)

    items = [
        Item(repo="test/repo", number=101, type="issue", title="Spam issue", body="buy now", raw={"labels": [{"name": "spam"}]}),
        Item(repo="test/repo", number=102, type="pull_request", title="Merged fix", body="fix", raw={"pull_request": {"merged_at": "2026-01-01"}}),
    ]

    count = populate_proxy_ground_truth(conn, items)
    assert count == 2

    gt_all = get_all_ground_truth(conn)
    assert len(gt_all) == 2
    # Check proxy labels
    labels = {v["label"] for v in gt_all.values()}
    assert "low_effort" in labels
    assert "ready_for_review" in labels

    # Create gold labels CSV
    csv_file = tmp_path / "gold.csv"
    with csv_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["item_id", "repo", "number", "gold_label"])
        writer.writeheader()
        writer.writerow({"item_id": "test/repo#101", "repo": "test/repo", "number": "101", "gold_label": "low_effort"})

    loaded = load_gold_labels_from_csv(conn, csv_file)
    assert loaded == 1

    gt_gold = get_all_ground_truth(conn, source="gold")
    assert len(gt_gold) == 1

    conn.close()
