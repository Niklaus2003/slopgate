"""Backtest runner for SlopGate triage models.

Replays historical items, computes bounded state and deterministic facts,
executes the Decider cascade, plans routine actions, and logs all decisions
into SQLite without ever executing actions or writing to GitHub.
Follows: architecture.md §7.3, implementation-plan.md Phase 8 Step 4.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3

    from slopgate.config import PolicyConfig
    from slopgate.decider.client import DeciderClient
    from slopgate.models import ActionPlan, DeciderResult, Item
    from slopgate.state.repo_index import RepoIndex

from slopgate.decider.cascade import run_cascade
from slopgate.decider.questions import hash_question_text
from slopgate.policy.gate import ConfidenceGate
from slopgate.state.builder import build_state
from slopgate.store.db import (
    save_decision,
    save_item,
    update_item_status,
)
from slopgate.worker import plan_item_actions

logger = logging.getLogger(__name__)


@dataclass
class BacktestItemSummary:
    """Per-item result from backtest evaluation."""

    item_id: int
    repo: str
    number: int
    item_type: str
    state_hash: str
    q1_answer: str
    q1_confidence: float
    overall_band: str
    overall_action: str
    decisions: list[DeciderResult]
    plan: ActionPlan
    latency_ms: float
    from_cache_count: int


@dataclass
class BacktestResult:
    """Aggregated statistics from a backtest run."""

    total_items: int = 0
    total_decisions: int = 0
    cache_hits: int = 0
    duration_seconds: float = 0.0
    items_summary: list[BacktestItemSummary] = field(default_factory=list)
    band_counts: dict[str, int] = field(
        default_factory=lambda: {"high": 0, "medium": 0, "low": 0}
    )
    verdict_counts: dict[str, int] = field(
        default_factory=lambda: {
            "proceed": 0,
            "proceed_soft": 0,
            "confirm": 0,
            "guide": 0,
            "deny": 0,
        }
    )
    latencies_ms: list[float] = field(default_factory=list)

    @property
    def cache_hit_rate_pct(self) -> float:
        if self.total_decisions == 0:
            return 0.0
        return (self.cache_hits / self.total_decisions) * 100.0


def run_backtest(
    items: list[Item],
    conn: sqlite3.Connection,
    policy: PolicyConfig,
    decider: DeciderClient,
    repo_index: RepoIndex | None = None,
    limit: int | None = None,
) -> BacktestResult:
    """Execute offline replay backtest on items, logging decisions into SQLite.

    CRITICAL INVARIANT: Never writes actions to GitHub or the `actions` execution table.
    """
    start_time = time.perf_counter()
    gate = ConfidenceGate()

    selected_items = items[:limit] if limit and limit > 0 else items
    result = BacktestResult(total_items=len(selected_items))

    for item in selected_items:
        t0 = time.perf_counter()
        item_id = save_item(conn, item)

        # 1. State Construction & Fact Extraction
        state = build_state(item, policy=policy, repo_index=repo_index)
        with conn:
            conn.execute(
                "UPDATE items SET state_text = ?, state_hash = ? WHERE id = ?",
                (state.text, state.hash, item_id),
            )

        # 2. Run Decider question cascade
        item_decisions = run_cascade(item, state, decider, policy)
        result.total_decisions += len(item_decisions)
        cache_hits_item = sum(1 for d in item_decisions if getattr(d, "from_cache", False))
        result.cache_hits += cache_hits_item

        # 3. Plan actions & evaluate safety gate verdicts
        plan = plan_item_actions(item, item_decisions, policy, gate)

        # 4. Save decisions to database with gate verdict
        for dec in item_decisions:
            verdict = gate.evaluate(
                tool_name="apply_label",
                decisions=[dec],
                policy=policy,
            )
            q_hash = hash_question_text(dec.question_id)
            save_decision(
                conn,
                item_id=item_id,
                decision=dec,
                verdict=verdict,
                question_text_hash=q_hash,
                state_hash=state.hash,
            )

        # 5. Record status in items table as 'decided' (NOT executed)
        update_item_status(conn, item_id, "decided")

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        result.latencies_ms.append(elapsed_ms)

        # Determine Q1 and overall band
        q1_dec = next((d for d in item_decisions if d.question_id == "Q1" or d.question_id.startswith("Q1")), item_decisions[0])
        q1_verdict = gate.evaluate(tool_name="apply_label", decisions=[q1_dec], policy=policy)
        overall_band = q1_verdict.band.value if hasattr(q1_verdict.band, "value") else str(q1_verdict.band).lower()
        overall_action = (
            plan.overall.value if hasattr(plan.overall, "value") else str(plan.overall).lower()
        )
        result.band_counts[overall_band] = result.band_counts.get(overall_band, 0) + 1
        result.verdict_counts[overall_action] = (
            result.verdict_counts.get(overall_action, 0) + 1
        )

        summary = BacktestItemSummary(
            item_id=item_id,
            repo=item.repo,
            number=item.number,
            item_type=item.type,
            state_hash=state.hash,
            q1_answer=str(q1_dec.answer),
            q1_confidence=float(q1_dec.confidence or 0.0),
            overall_band=overall_band,
            overall_action=overall_action,
            decisions=item_decisions,
            plan=plan,
            latency_ms=elapsed_ms,
            from_cache_count=cache_hits_item,
        )
        result.items_summary.append(summary)

    result.duration_seconds = time.perf_counter() - start_time
    return result
