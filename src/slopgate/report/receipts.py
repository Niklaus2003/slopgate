"""Receipt generator for SlopGate triage runs.

Builds structured JSON receipts and human-readable Markdown summaries
from SQLite audit and decision tables.
Follows: architecture.md §6.8, §7.1, docs/defense/04_DATA.md.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from slopgate.store.db import (
    get_actions_for_item,
    get_decisions_for_item,
    get_escalations_for_item,
    get_item_by_id,
)


def build_item_receipt(conn: sqlite3.Connection, item_id: int) -> dict[str, Any]:
    """Compile a complete JSON receipt for a processed item from database records."""
    item = get_item_by_id(conn, item_id)
    if not item:
        raise ValueError(f"Item with id {item_id} not found in database.")

    raw_item_row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    state_hash = raw_item_row["state_hash"] if raw_item_row else ""
    state_text = raw_item_row["state_text"] if raw_item_row else ""

    decisions = get_decisions_for_item(conn, item_id)
    actions = get_actions_for_item(conn, item_id)
    escalations = get_escalations_for_item(conn, item_id)

    pending_rows = conn.execute(
        "SELECT * FROM pending_approvals WHERE item_id = ? ORDER BY id ASC", (item_id,)
    ).fetchall()
    pending_approvals = [dict(r) for r in pending_rows]

    # Calculate summary metrics
    total_decider_latency = sum(float(d.get("latency_ms") or 0.0) for d in decisions)
    cache_hits = sum(1 for d in decisions if d.get("from_cache"))
    total_bedrock_cost = sum(float(e.get("est_cost_usd") or 0.0) for e in escalations)

    # Determine overall band and action
    bands = [d.get("band") for d in decisions if d.get("band")]
    if "low" in bands:
        overall_band = "low"
    elif "medium" in bands:
        overall_band = "medium"
    elif "high" in bands:
        overall_band = "high"
    else:
        overall_band = "unknown"

    actions_list = [d.get("gate_action") for d in decisions if d.get("gate_action")]
    if "deny" in actions_list:
        overall_action = "deny"
    elif "confirm" in actions_list:
        overall_action = "confirm"
    elif "guide" in actions_list:
        overall_action = "guide"
    elif "proceed_soft" in actions_list:
        overall_action = "proceed_soft"
    elif "proceed" in actions_list:
        overall_action = "proceed"
    else:
        overall_action = "confirm"

    return {
        "receipt_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "item": {
            "id": item_id,
            "repo": item.repo,
            "number": item.number,
            "type": item.type,
            "title": item.title,
            "created_at": item.created_at,
            "status": item.status,
            "state_hash": state_hash,
            "approx_tokens": len(state_text) // 4 if state_text else 0,
        },
        "summary": {
            "status": item.status,
            "overall_band": overall_band,
            "overall_action": overall_action,
            "total_decisions": len(decisions),
            "cache_hits": cache_hits,
            "total_decider_latency_ms": round(total_decider_latency, 2),
            "total_bedrock_cost_usd": round(total_bedrock_cost, 6),
            "actions_recorded": len(actions),
            "pending_approvals_count": len(pending_approvals),
        },
        "decisions": decisions,
        "actions": actions,
        "escalations": escalations,
        "pending_approvals": pending_approvals,
    }


def render_markdown_receipt(receipt: dict[str, Any]) -> str:
    """Format a receipt into a GitHub-flavored Markdown audit document."""
    item = receipt["item"]
    summary = receipt["summary"]
    decisions = receipt.get("decisions", [])
    actions = receipt.get("actions", [])
    escalations = receipt.get("escalations", [])
    pending = receipt.get("pending_approvals", [])

    lines: list[str] = []
    lines.append(f"# SlopGate Triage Receipt: {item['repo']}#{item['number']}")
    lines.append("")
    lines.append(
        f"> **Status:** `{summary['status'].upper()}` | "
        f"**Band:** `{summary['overall_band'].upper()}` | "
        f"**Action:** `{summary['overall_action'].upper()}`"
    )
    lines.append(
        f"> **Title:** {item['title']}  \n"
        f"> **State Hash:** `{item['state_hash'][:16]}...` | "
        f"**Generated:** {receipt['generated_at'][:19]}Z"
    )
    lines.append("")

    # Decisions Table
    lines.append("## 🧠 Model Inferences & Safety Verdicts")
    if not decisions:
        lines.append("*No decisions recorded.*")
    else:
        lines.append(
            "| Question | Answer | Confidence | Band | Gate Action | Reason | Latency | Cache |"
        )
        lines.append(
            "|:---|:---|:---|:---|:---|:---|:---|:---|"
        )
        for d in decisions:
            conf_str = f"{d['confidence']:.2f}" if d.get("confidence") is not None else "N/A"
            cache_icon = "⚡ Hit" if d.get("from_cache") else "Cold"
            lines.append(
                f"| `{d['question_id']}` | **{d['answer']}** | {conf_str} | "
                f"`{str(d['band']).upper()}` | `{str(d['gate_action']).upper()}` | "
                f"{d.get('gate_reason', '')} | {d.get('latency_ms', 0):.1f}ms | {cache_icon} |"
            )
    lines.append("")

    # Actions Table
    lines.append("## ⚡ Actions & Audit Trail")
    if not actions:
        lines.append("*No automated actions executed.*")
    else:
        lines.append("| Tool | Arguments | Handler Result | Mode | Idempotency Key |")
        lines.append("|:---|:---|:---|:---|:---|")
        for a in actions:
            mode = "Dry-Run" if a.get("dry_run") else "Live"
            args_snippet = a.get("args_json", "{}")
            if len(args_snippet) > 40:
                args_snippet = args_snippet[:37] + "..."
            lines.append(
                f"| `{a['tool']}` | `{args_snippet}` | `{a.get('handler_result')}` | "
                f"{mode} | `{a.get('idempotency_key', '')}` |"
            )
    lines.append("")

    # Escalations Section
    if escalations:
        lines.append("## ☁️ Amazon Bedrock Escalations")
        for e in escalations:
            lines.append(
                f"- **Purpose:** `{e['purpose']}` | **Model:** `{e['bedrock_model']}` | "
                f"**Tokens:** {e['tokens_in']} in / {e['tokens_out']} out | "
                f"**Est. Cost:** ${e['est_cost_usd']:.5f}"
            )
            output_snippet = (e.get("output_text") or "").strip()
            if output_snippet:
                lines.append(f"  > *Draft Output:* {output_snippet[:150]}...")
        lines.append("")

    # Pending Approvals Section
    if pending:
        lines.append("## 👤 Maintainer Review Status")
        for p in pending:
            lines.append(
                f"- **Approval #{p['id']}:** Status = `{p['status'].upper()}`  \n"
                f"  *Receipt Notes:* {p.get('receipt_md', 'None')}"
            )
        lines.append("")

    return "\n".join(lines)


def export_receipt_to_disk(
    receipt: dict[str, Any],
    output_dir: str | Path = "reports/receipts",
    as_markdown: bool = True,
) -> Path:
    """Save receipt JSON or Markdown to target directory."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    item = receipt["item"]
    safe_repo = item["repo"].replace("/", "_")
    base_name = f"{safe_repo}_{item['number']}"

    if as_markdown:
        file_path = out_path / f"{base_name}.md"
        content = render_markdown_receipt(receipt)
        file_path.write_text(content, encoding="utf-8")
    else:
        file_path = out_path / f"{base_name}.json"
        content = json.dumps(receipt, indent=2)
        file_path.write_text(content, encoding="utf-8")

    return file_path
