"""SQLite repository and storage helpers for SlopGate.

Implements WAL mode, transactional helpers, crash-recovery, and caching.
Follows: architecture.md §5.3, docs/defense/04_DATA.md.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from slopgate.models import (
    DeciderResult,
    GateVerdict,
    Item,
    ItemStatus,
)

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def init_db(target: str | Path | sqlite3.Connection = "data/slopgate.db") -> sqlite3.Connection:
    """Initialize SQLite database with schema, WAL mode, and pragma settings."""
    if isinstance(target, sqlite3.Connection):
        conn = target
    else:
        path = Path(target)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=30.0)

    conn.row_factory = sqlite3.Row
    # PRAGMA statements
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA synchronous = NORMAL;")

    # Auto-migrate older databases if needed before applying indices
    cols = [r[1] for r in conn.execute("PRAGMA table_info(decisions)").fetchall()]
    if cols and "state_hash" not in cols:
        conn.execute("ALTER TABLE decisions ADD COLUMN state_hash TEXT;")
        conn.commit()

    # Apply schema
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.commit()
    return conn


def get_connection(db_path: str | Path = "data/slopgate.db") -> sqlite3.Connection:
    """Get initialized database connection."""
    return init_db(db_path)


def reset_stale_processing(conn: sqlite3.Connection) -> int:
    """Crash-recovery helper: reset any abandoned 'processing' items back to 'queued'."""
    with conn:
        cursor = conn.execute(
            """
            UPDATE items
            SET status = 'queued', processing_started_at = NULL
            WHERE status = 'processing'
            """
        )
        return cursor.rowcount


# ---------------------------------------------------------------------------
# Items Repository
# ---------------------------------------------------------------------------


def save_item(
    conn: sqlite3.Connection,
    item: Item,
    state_text: str = "",
    state_hash: str = "",
) -> int:
    """Insert or update an Item in the database. Returns the item's integer id."""
    raw_json = json.dumps(item.raw) if item.raw else "{}"
    with conn:
        conn.execute(
            """
            INSERT INTO items (
                repo, number, type, title, body, created_at, state_text, state_hash, status, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(repo, number) DO UPDATE SET
                type = excluded.type,
                title = excluded.title,
                body = excluded.body,
                created_at = excluded.created_at,
                state_text = CASE WHEN excluded.state_text != '' THEN excluded.state_text ELSE items.state_text END,
                state_hash = CASE WHEN excluded.state_hash != '' THEN excluded.state_hash ELSE items.state_hash END,
                status = excluded.status,
                raw_json = excluded.raw_json
            """,
            (
                item.repo,
                item.number,
                item.type,
                item.title,
                item.body,
                item.created_at,
                state_text,
                state_hash,
                item.status,
                raw_json,
            ),
        )

        row = conn.execute(
            "SELECT id FROM items WHERE repo = ? AND number = ?",
            (item.repo, item.number),
        ).fetchone()
        return int(row["id"]) if row else 0


def get_item_by_id(conn: sqlite3.Connection, item_id: int) -> Item | None:
    """Retrieve an Item by database primary key ID."""
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        return None
    raw_dict = json.loads(row["raw_json"]) if row["raw_json"] else {}
    return Item(
        repo=row["repo"],
        number=row["number"],
        type=row["type"],
        title=row["title"] or "",
        body=row["body"] or "",
        created_at=row["created_at"] or "",
        raw=raw_dict,
        status=row["status"],
    )


def get_item_by_repo_number(
    conn: sqlite3.Connection, repo: str, number: int
) -> tuple[int, Item] | None:
    """Retrieve (item_id, Item) by repo and number."""
    row = conn.execute(
        "SELECT * FROM items WHERE repo = ? AND number = ?", (repo, number)
    ).fetchone()
    if not row:
        return None
    raw_dict = json.loads(row["raw_json"]) if row["raw_json"] else {}
    item = Item(
        repo=row["repo"],
        number=row["number"],
        type=row["type"],
        title=row["title"] or "",
        body=row["body"] or "",
        created_at=row["created_at"] or "",
        raw=raw_dict,
        status=row["status"],
    )
    return int(row["id"]), item


def list_items_by_status(
    conn: sqlite3.Connection, status: ItemStatus, limit: int = 50
) -> list[dict[str, Any]]:
    """List items with a specific status."""
    rows = conn.execute(
        "SELECT * FROM items WHERE status = ? ORDER BY id ASC LIMIT ?",
        (status, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def update_item_status(
    conn: sqlite3.Connection, item_id: int, status: ItemStatus
) -> None:
    """Update status of an item."""
    with conn:
        conn.execute(
            "UPDATE items SET status = ? WHERE id = ?",
            (status, item_id),
        )


# ---------------------------------------------------------------------------
# Decisions Repository & Cache
# ---------------------------------------------------------------------------


def save_decision(
    conn: sqlite3.Connection,
    item_id: int,
    decision: DeciderResult,
    verdict: GateVerdict | None = None,
    question_text_hash: str = "",
    state_hash: str = "",
) -> int:
    """Record a Decider inference result and optional Gate verdict."""
    probs_json = json.dumps(decision.probs)
    answer_str = str(decision.answer)
    gate_action = verdict.action.value if verdict else None
    gate_reason = verdict.reason if verdict else None
    band = verdict.band.value if verdict else (decision.confidence and "high")

    with conn:
        cursor = conn.execute(
            """
            INSERT INTO decisions (
                item_id, question_id, qtype, question_text_hash, state_hash,
                answer, probs_json, confidence, band,
                gate_action, gate_reason, latency_ms,
                model_id, from_cache
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id if item_id and item_id > 0 else None,
                decision.question_id,
                decision.qtype,
                question_text_hash,
                state_hash,
                answer_str,
                probs_json,
                decision.confidence,
                band,
                gate_action,
                gate_reason,
                decision.latency_ms,
                decision.model_id,
                1 if decision.from_cache else 0,
            ),
        )
        return cursor.lastrowid or 0


def get_cached_decision(
    conn: sqlite3.Connection,
    question_id: str,
    question_text_hash: str,
    model_id: str,
    state_hash: str | None = None,
) -> DeciderResult | None:
    """Lookup a previously cached Decider result keyed by question or state."""
    if state_hash:
        row = conn.execute(
            """
            SELECT * FROM decisions
            WHERE (state_hash = ? OR item_id IN (SELECT id FROM items WHERE state_hash = ?))
              AND question_id = ?
              AND question_text_hash = ?
              AND (model_id = ? OR model_id LIKE 'StrandsAgents%' OR model_id = 'fake-decider-2b')
            ORDER BY CASE WHEN model_id = ? THEN 0 ELSE 1 END, id DESC LIMIT 1
            """,
            (state_hash, state_hash, question_id, question_text_hash, model_id, model_id),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT * FROM decisions
            WHERE question_id = ? AND question_text_hash = ?
              AND (model_id = ? OR model_id LIKE 'StrandsAgents%' OR model_id = 'fake-decider-2b')
            ORDER BY CASE WHEN model_id = ? THEN 0 ELSE 1 END, id DESC LIMIT 1
            """,
            (question_id, question_text_hash, model_id, model_id),
        ).fetchone()

    if not row:
        return None

    probs = json.loads(row["probs_json"]) if row["probs_json"] else {}
    answer: str | bool = row["answer"]
    if row["qtype"] == "noul":
        answer = answer.lower() in ("true", "1", "yes")

    return DeciderResult(
        question_id=row["question_id"],
        qtype=row["qtype"],
        answer=answer,
        probs=probs,
        confidence=row["confidence"],
        latency_ms=row["latency_ms"] or 0.0,
        model_id=row["model_id"] or "",
        from_cache=True,
    )


# ---------------------------------------------------------------------------
# Actions Repository & Idempotency
# ---------------------------------------------------------------------------


def save_action(
    conn: sqlite3.Connection,
    item_id: int,
    tool: str,
    args: dict[str, Any],
    handler_result: str,
    dry_run: bool = True,
    idempotency_key: str | None = None,
) -> bool:
    """Record an action execution.

    Returns:
        True if action was saved.
        False if skipped due to duplicate idempotency_key.
    """
    args_json = json.dumps(args)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO actions (
                    item_id, tool, args_json, handler_result, executed, dry_run, idempotency_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    tool,
                    args_json,
                    handler_result,
                    0 if dry_run else 1,
                    1 if dry_run else 0,
                    idempotency_key,
                ),
            )
        return True
    except sqlite3.IntegrityError:
        # Duplicate idempotency_key violation
        return False


def has_action_been_executed(
    conn: sqlite3.Connection,
    idempotency_key: str,
) -> bool:
    """Check if an action with this idempotency key was previously executed or recorded."""
    row = conn.execute(
        "SELECT id FROM actions WHERE idempotency_key = ? LIMIT 1",
        (idempotency_key,),
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Pending Approvals (Maintainer Inbox)
# ---------------------------------------------------------------------------


def save_pending_approval(
    conn: sqlite3.Connection,
    item_id: int,
    proposed_plan: dict[str, Any] | str,
    receipt_md: str = "",
) -> int:
    """Create a pending approval row for human review."""
    plan_json = proposed_plan if isinstance(proposed_plan, str) else json.dumps(proposed_plan)
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO pending_approvals (
                item_id, proposed_plan_json, receipt_md, status
            ) VALUES (?, ?, ?, 'pending')
            """,
            (item_id, plan_json, receipt_md),
        )
        return cursor.lastrowid or 0


def get_audit_log(
    conn: sqlite3.Connection, item_id: int | None = None
) -> list[dict[str, Any]]:
    """Retrieve recorded action audit entries."""
    if item_id is not None:
        rows = conn.execute(
            """
            SELECT a.*, a.tool as action, i.repo, i.number
            FROM actions a
            JOIN items i ON a.item_id = i.id
            WHERE a.item_id = ?
            ORDER BY a.id ASC
            """,
            (item_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT a.*, a.tool as action, i.repo, i.number
            FROM actions a
            JOIN items i ON a.item_id = i.id
            ORDER BY a.id ASC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def get_pending_approvals(
    conn: sqlite3.Connection, status: str = "pending"
) -> list[dict[str, Any]]:
    """Retrieve pending approval items for maintainer inspection."""
    rows = conn.execute(
        """
        SELECT p.*, i.repo, i.number, i.title, i.type
        FROM pending_approvals p
        JOIN items i ON p.item_id = i.id
        WHERE p.status = ?
        ORDER BY p.id ASC
        """,
        (status,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_pending_approval_by_id(
    conn: sqlite3.Connection, approval_id: int
) -> dict[str, Any] | None:
    """Retrieve a single pending approval by its primary key ID."""
    row = conn.execute(
        """
        SELECT p.*, i.repo, i.number, i.title, i.type
        FROM pending_approvals p
        JOIN items i ON p.item_id = i.id
        WHERE p.id = ?
        """,
        (approval_id,),
    ).fetchone()
    return dict(row) if row else None


def update_pending_approval_status(
    conn: sqlite3.Connection, approval_id: int, status: str
) -> None:
    """Approve or reject a pending approval."""
    with conn:
        conn.execute(
            """
            UPDATE pending_approvals
            SET status = ?, decided_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, approval_id),
        )


# ---------------------------------------------------------------------------
# Escalations (Bedrock Usage Log)
# ---------------------------------------------------------------------------


def save_escalation(
    conn: sqlite3.Connection,
    item_id: int,
    purpose: str,
    bedrock_model: str,
    tokens_in: int,
    tokens_out: int,
    latency_ms: float,
    est_cost_usd: float,
    output_text: str,
) -> int:
    """Log Bedrock invocation token usage and latency."""
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO escalations (
                item_id, purpose, bedrock_model, tokens_in, tokens_out,
                latency_ms, est_cost_usd, output_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                purpose,
                bedrock_model,
                tokens_in,
                tokens_out,
                latency_ms,
                est_cost_usd,
                output_text,
            ),
        )
        return cursor.lastrowid or 0


def get_escalations_for_item(
    conn: sqlite3.Connection, item_id: int
) -> list[dict[str, Any]]:
    """Retrieve all logged Bedrock escalations for an item."""
    rows = conn.execute(
        "SELECT * FROM escalations WHERE item_id = ? ORDER BY id ASC",
        (item_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Ground Truth (Backtesting Data)
# ---------------------------------------------------------------------------


def save_ground_truth(
    conn: sqlite3.Connection, item_id: int, label: str, source: str = "proxy"
) -> None:
    """Save proxy or human gold label for an item."""
    with conn:
        conn.execute(
            """
            INSERT INTO ground_truth (item_id, label, source)
            VALUES (?, ?, ?)
            ON CONFLICT(item_id) DO UPDATE SET
                label = excluded.label,
                source = excluded.source
            """,
            (item_id, label, source),
        )


def get_ground_truth(
    conn: sqlite3.Connection, item_id: int
) -> dict[str, Any] | None:
    """Retrieve ground truth label for an item."""
    row = conn.execute(
        "SELECT * FROM ground_truth WHERE item_id = ?", (item_id,)
    ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Worker Queue & Reporting Helpers
# ---------------------------------------------------------------------------


def get_decisions_for_item(
    conn: sqlite3.Connection, item_id: int
) -> list[dict[str, Any]]:
    """Retrieve all decisions recorded for an item."""
    rows = conn.execute(
        "SELECT * FROM decisions WHERE item_id = ? ORDER BY id ASC",
        (item_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_actions_for_item(
    conn: sqlite3.Connection, item_id: int
) -> list[dict[str, Any]]:
    """Retrieve all actions recorded for an item."""
    rows = conn.execute(
        "SELECT * FROM actions WHERE item_id = ? ORDER BY id ASC",
        (item_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def pop_next_queued_item(
    conn: sqlite3.Connection,
) -> tuple[int, Item] | None:
    """Atomically pop the next queued item and mark it as processing."""
    with conn:
        row = conn.execute(
            """
            SELECT * FROM items
            WHERE status = 'queued'
            ORDER BY id ASC
            LIMIT 1
            """
        ).fetchone()
        if not row:
            return None

        item_id = int(row["id"])
        conn.execute(
            """
            UPDATE items
            SET status = 'processing', processing_started_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (item_id,),
        )
        raw_dict = json.loads(row["raw_json"]) if row["raw_json"] else {}
        item = Item(
            repo=row["repo"],
            number=row["number"],
            type=row["type"],
            title=row["title"] or "",
            body=row["body"] or "",
            created_at=row["created_at"] or "",
            raw=raw_dict,
            status="processing",
        )
        return item_id, item


def count_items_by_status(conn: sqlite3.Connection) -> dict[str, int]:
    """Count items grouped by status."""
    rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM items GROUP BY status"
    ).fetchall()
    return {r["status"]: int(r["cnt"]) for r in rows}


def get_all_item_ids(conn: sqlite3.Connection) -> list[int]:
    """Retrieve all item integer primary key IDs."""
    rows = conn.execute("SELECT id FROM items ORDER BY id ASC").fetchall()
    return [int(r["id"]) for r in rows]





def get_all_ground_truth(
    conn: sqlite3.Connection, source: str | None = None
) -> dict[int, dict[str, str]]:
    """Retrieve all ground truth records, optionally filtered by source ('proxy' or 'gold')."""
    if source:
        rows = conn.execute(
            "SELECT * FROM ground_truth WHERE source = ? ORDER BY item_id ASC", (source,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM ground_truth ORDER BY item_id ASC"
        ).fetchall()
    return {
        int(r["item_id"]): {
            "item_id": int(r["item_id"]),
            "label": r["label"],
            "source": r["source"],
        }
        for r in rows
    }


def get_escalations_by_purpose(
    conn: sqlite3.Connection, purpose: str = "baseline"
) -> list[dict[str, Any]]:
    """Fetch escalation records filtered by purpose (e.g. 'baseline')."""
    rows = conn.execute(
        "SELECT * FROM escalations WHERE purpose = ? ORDER BY id ASC", (purpose,)
    ).fetchall()
    return [dict(r) for r in rows]

