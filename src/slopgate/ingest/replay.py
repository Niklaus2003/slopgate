"""Offline replay source and snapshot utilities for reproducible backtesting.

Follows: architecture.md §6.1, PLAN_REVIEW.md §2.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from slopgate.ingest.github import GitHubClient, _parse_github_item
from slopgate.models import Item


def load_replay_items(path: str | Path) -> list[Item]:
    """Load items from a saved offline JSON snapshot."""
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Replay snapshot file not found: {file_path}")

    raw_data = json.loads(file_path.read_text(encoding="utf-8"))
    items: list[Item] = []

    for entry in raw_data:
        if "repo" in entry and "raw" in entry:
            # Serialized SlopGate Item dict
            items.append(Item.model_validate(entry))
        elif "url" in entry or "number" in entry:
            # Raw GitHub REST API JSON dict
            repo = entry.get("repository_url", "").split("/repos/")[-1] or "pallets/flask"
            items.append(_parse_github_item(repo, entry))
        else:
            items.append(Item.model_validate(entry))

    return items


def save_replay_items(items: list[Item], output_path: str | Path) -> None:
    """Save items to an offline JSON snapshot."""
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    serialized = [item.model_dump() for item in items]
    dest.write_text(json.dumps(serialized, indent=2), encoding="utf-8")


def snapshot_repository(
    repo: str,
    output_items_path: str | Path,
    output_tree_path: str | Path,
    limit: int = 100,
    token: str | None = None,
) -> tuple[int, int]:
    """Snapshot a repository's issues/PRs and its file tree for 100% offline backtesting."""
    client = GitHubClient(token=token)

    # 1. Fetch items
    items, _ = client.fetch_issues(repo=repo, limit=limit)
    save_replay_items(items, output_items_path)

    # 2. Fetch file tree
    tree_paths = client.fetch_repo_tree(repo=repo)
    tree_dest = Path(output_tree_path)
    tree_dest.parent.mkdir(parents=True, exist_ok=True)
    tree_dest.write_text(json.dumps(tree_paths, indent=2), encoding="utf-8")

    return len(items), len(tree_paths)


def export_gold_candidates_csv(
    items: list[Item],
    output_csv_path: str | Path,
    limit: int = 60,
) -> int:
    """Export candidate items to a CSV template for human gold labeling."""
    dest = Path(output_csv_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "item_id",
        "repo",
        "number",
        "type",
        "title",
        "body_preview",
        "maintainer_labels",
        "suggested_label",
        "gold_label",
        "notes",
    ]

    count = 0
    with dest.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for item in items[:limit]:
            raw_labels = item.raw.get("labels", []) if isinstance(item.raw, dict) else []
            label_names = [
                lbl.get("name", "") if isinstance(lbl, dict) else str(lbl)
                for lbl in raw_labels
            ]

            from slopgate.backtest.proxy import map_item_to_proxy_label

            suggested = map_item_to_proxy_label(item)
            body_preview = " ".join((item.body or "").split())[:200]
            writer.writerow(
                {
                    "item_id": item.id,
                    "repo": item.repo,
                    "number": item.number,
                    "type": item.type,
                    "title": item.title,
                    "body_preview": body_preview,
                    "maintainer_labels": ";".join(filter(None, label_names)),
                    "suggested_label": suggested,
                    "gold_label": "",
                    "notes": "",
                }
            )
            count += 1

    return count
