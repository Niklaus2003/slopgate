"""Background triage worker for SlopGate.

Processes queued issues/PRs end-to-end:
pop -> build_state -> cascade -> plan -> execute_or_escalate -> receipt -> status.
Implements crash recovery, graceful shutdown on SIGINT, and run summary reporting.

Follows: architecture.md §3, §7, docs/defense/03_FLOW.md.
"""

from __future__ import annotations

import logging
import signal
import sqlite3
import time
from collections.abc import Callable
from types import FrameType
from typing import Any

from slopgate.agent.executor import ScriptedExecutor
from slopgate.agent.tools import flag_for_maintainer
from slopgate.bedrock.budget import BudgetGuard
from slopgate.bedrock.client import BedrockClient
from slopgate.bedrock.escalate import draft_reply, reason_on_ambiguous
from slopgate.config import PolicyConfig
from slopgate.decider.cascade import run_cascade
from slopgate.decider.client import DeciderClient
from slopgate.decider.questions import hash_question_text
from slopgate.models import (
    ActionKind,
    ActionPlan,
    DeciderResult,
    Item,
    PlannedToolCall,
)
from slopgate.policy.gate import ConfidenceGate
from slopgate.policy.resolver import build_action_plan
from slopgate.report.summary import RunSummary, calculate_percentiles
from slopgate.state.builder import build_state
from slopgate.state.repo_index import RepoIndex
from slopgate.store.db import (
    get_actions_for_item,
    get_decisions_for_item,
    get_escalations_for_item,
    pop_next_queued_item,
    reset_stale_processing,
    save_decision,
    save_pending_approval,
    update_item_status,
)

logger = logging.getLogger(__name__)


def plan_item_actions(
    item: Item,
    results: list[DeciderResult],
    policy: PolicyConfig,
    gate: ConfidenceGate,
) -> ActionPlan:
    """Determine planned tool calls and evaluate policy gate verdicts for an item."""
    q1_result = next((r for r in results if r.question_id == "Q1" or r.question_id.startswith("Q1")), None)
    item_kind = str(q1_result.answer) if q1_result else "unknown"

    planned_steps: list[PlannedToolCall] = []

    # Map item classification into candidate tool steps
    if item_kind == "real_bug_report":
        # Check N1 reproduction follow-up if present
        n1_result = next((r for r in results if r.question_id == "N1"), None)
        has_repro = n1_result.answer is True if n1_result else True

        if has_repro:
            planned_steps.append(
                PlannedToolCall(
                    tool_name="apply_label",
                    args={"label": policy.labels.get("triaged", "triaged")},
                )
            )
        else:
            planned_steps.append(
                PlannedToolCall(
                    tool_name="apply_label",
                    args={"label": policy.labels.get("needs_info", "needs-info")},
                )
            )
            planned_steps.append(
                PlannedToolCall(
                    tool_name="request_info_comment",
                    args={
                        "template_type": "bug",
                        "missing_fields": ["Minimal reproduction steps", "Expected behavior"],
                    },
                )
            )

    elif item_kind == "support_question":
        planned_steps.append(
            PlannedToolCall(
                tool_name="apply_label",
                args={"label": policy.labels.get("question", "question")},
            )
        )
        planned_steps.append(
            PlannedToolCall(
                tool_name="post_comment",
                args={
                    "body": (
                        "Thank you for opening this issue! For usage questions or general assistance, "
                        "please check the community discussions or forum."
                    )
                },
            )
        )

    elif item_kind == "likely_duplicate":
        planned_steps.append(
            PlannedToolCall(
                tool_name="apply_label",
                args={"label": "duplicate"},
            )
        )
        planned_steps.append(
            PlannedToolCall(
                tool_name="flag_for_maintainer",
                args={
                    "reason": "Potential duplicate contribution; maintainer verification required.",
                    "suggested_action": "verify_duplicate",
                },
            )
        )

    elif item_kind == "low_effort":
        planned_steps.append(
            PlannedToolCall(
                tool_name="apply_label",
                args={"label": policy.labels.get("low_effort", "needs-more-detail")},
            )
        )
        planned_steps.append(
            PlannedToolCall(
                tool_name="request_info_comment",
                args={
                    "template_type": "general",
                    "missing_fields": ["Detailed problem description", "Minimal reproducible example"],
                },
            )
        )

    elif item_kind == "security_report":
        planned_steps.append(
            PlannedToolCall(
                tool_name="flag_for_maintainer",
                args={
                    "reason": "Potential security vulnerability report; requires private disclosure review.",
                    "suggested_action": "security_review",
                },
            )
        )

    elif item_kind == "ready_for_review":
        planned_steps.append(
            PlannedToolCall(
                tool_name="apply_label",
                args={"label": policy.labels.get("ready", "ready-for-review")},
            )
        )

    else:
        # Fallback for general or unclassified items
        planned_steps.append(
            PlannedToolCall(
                tool_name="flag_for_maintainer",
                args={
                    "reason": f"Classified as '{item_kind}'; requires maintainer review.",
                    "suggested_action": "review",
                },
            )
        )

    # Evaluate gate verdict for each planned step
    verdicts = [gate.evaluate(step.tool_name, results, policy) for step in planned_steps]

    return build_action_plan(verdicts, planned_steps=planned_steps)


class Worker:
    """Processes queued triage items end-to-end."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        policy: PolicyConfig,
        decider: DeciderClient | None = None,
        bedrock_client: BedrockClient | None = None,
        budget: BudgetGuard | None = None,
        repo_index: RepoIndex | None = None,
        dry_run: bool = True,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.conn = conn
        self.policy = policy
        self.decider = decider or self._init_decider()
        self.bedrock_client = bedrock_client or BedrockClient()
        self.budget = budget or BudgetGuard()
        self.repo_index = repo_index
        self.dry_run = dry_run
        self.on_progress = on_progress

        self.gate = ConfidenceGate()
        self.executor = ScriptedExecutor(gate=self.gate, policy=self.policy)
        self._stop_requested = False

    def _init_decider(self) -> DeciderClient:
        """Initialize local in-process Decider engine."""
        from slopgate.decider.in_process import InProcessDecider

        return InProcessDecider(conn=self.conn)

    def _handle_shutdown(self, signum: int, frame: FrameType | None) -> None:
        """Handle termination signal gracefully."""
        logger.warning("Shutdown signal received (%s). Finishing active item and stopping worker...", signum)
        self._stop_requested = True

    def process_item(self, item_id: int, item: Item) -> str:
        """Execute full triage pipeline for a single item."""
        logger.info("Processing item %s#%d (id=%d)...", item.repo, item.number, item_id)

        try:
            # 1. State Construction & Fact Extraction
            state = build_state(item, policy=self.policy, repo_index=self.repo_index)
            with self.conn:
                self.conn.execute(
                    "UPDATE items SET state_text = ?, state_hash = ? WHERE id = ?",
                    (state.text, state.hash, item_id),
                )

            # 2. Decider Cascade Inference
            results = run_cascade(item, state, self.decider, self.policy)

            # Persist decisions to SQLite
            for res in results:
                q_text_hash = hash_question_text(res.question_id)
                verdict = self.gate.evaluate(
                    tool_name="apply_label",
                    decisions=[res],
                    policy=self.policy,
                )
                save_decision(
                    conn=self.conn,
                    item_id=item_id,
                    decision=res,
                    verdict=verdict,
                    question_text_hash=q_text_hash,
                    state_hash=state.hash,
                )

            # 3. Action Planning & Policy Gating
            plan = plan_item_actions(item, results, self.policy, self.gate)
            overall_action = plan.overall

            # 4. Execution or Escalation Routing
            if overall_action in (ActionKind.PROCEED, ActionKind.PROCEED_SOFT):
                # Routine path: Execute planned tools
                if plan.needs_bedrock_draft:
                    draft = draft_reply(
                        item=item,
                        receipt_notes=plan.receipt_notes,
                        template_hint=str(results[0].answer) if results else "",
                        client=self.bedrock_client,
                        budget=self.budget,
                        conn=self.conn,
                        item_id=item_id,
                    )
                    # Update body of any planned comment step
                    for step in plan.steps:
                        if step.tool_name == "post_comment":
                            step.args["body"] = draft

                report = self.executor.execute_plan(
                    item=item,
                    plan=plan,
                    results=results,
                    conn=self.conn,
                    item_id=item_id,
                    dry_run=self.dry_run,
                )

                if report.overall_status == "pending_approval":
                    final_status = "pending_approval"
                else:
                    final_status = "executed"

            elif overall_action in (ActionKind.GUIDE, ActionKind.CONFIRM):
                # Escalation path: route to maintainer review
                if overall_action is ActionKind.GUIDE or plan.needs_bedrock_reasoning:
                    probs_dict = results[0].probs if results else {}
                    reasoning = reason_on_ambiguous(
                        item=item,
                        facts=state.facts,
                        decider_probs=probs_dict,
                        client=self.bedrock_client,
                        budget=self.budget,
                        conn=self.conn,
                        item_id=item_id,
                    )
                    plan.receipt_notes.append(f"Bedrock Reasoning: {reasoning.get('rationale')}")

                save_pending_approval(
                    conn=self.conn,
                    item_id=item_id,
                    proposed_plan=plan.model_dump(),
                    receipt_md=f"Action requires review: {plan.overall.value.upper()}",
                )
                final_status = "pending_approval"

            else:  # DENY
                flag_for_maintainer(
                    repo=item.repo,
                    number=item.number,
                    reason="Action denied by policy gate invariants.",
                    suggested_action="maintainer_review",
                    dry_run=self.dry_run,
                    conn=self.conn,
                    item_id=item_id,
                )
                final_status = "flagged"

            update_item_status(self.conn, item_id, final_status)
            return final_status

        except Exception as err:
            logger.exception("Error processing item %s#%d", item.repo, item.number)
            flag_for_maintainer(
                repo=item.repo,
                number=item.number,
                reason=f"Processing exception: {err}",
                suggested_action="review_error",
                dry_run=self.dry_run,
                conn=self.conn,
                item_id=item_id,
            )
            update_item_status(self.conn, item_id, "error")
            return "error"

    def run(self, limit: int | None = None) -> RunSummary:
        """Drain the queued items from SQLite end-to-end."""
        # 1. Register signal handlers for graceful SIGINT/SIGTERM shutdown
        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)
        try:
            signal.signal(signal.SIGINT, self._handle_shutdown)
            signal.signal(signal.SIGTERM, self._handle_shutdown)
        except (ValueError, AttributeError):
            # Not in main thread or platform unsupported
            pass

        start_time = time.perf_counter()

        # 2. Crash recovery: reset stale 'processing' items
        stale_reset = reset_stale_processing(self.conn)
        if stale_reset > 0:
            logger.info("Crash recovery: reset %d abandoned 'processing' items back to 'queued'", stale_reset)

        processed_ids: list[int] = []
        status_counts = {"executed": 0, "pending_approval": 0, "flagged": 0, "dismissed": 0, "error": 0}

        try:
            while not self._stop_requested:
                if limit is not None and len(processed_ids) >= limit:
                    break

                popped = pop_next_queued_item(self.conn)
                if not popped:
                    # Queue is completely drained
                    break

                item_id, item = popped
                final_status = self.process_item(item_id, item)
                processed_ids.append(item_id)
                status_counts[final_status] = status_counts.get(final_status, 0) + 1

                if self.on_progress:
                    self.on_progress(
                        {
                            "item_id": item_id,
                            "repo": item.repo,
                            "number": item.number,
                            "status": final_status,
                            "completed": len(processed_ids),
                        }
                    )

        finally:
            # Restore original signal handlers
            try:
                signal.signal(signal.SIGINT, original_sigint)
                signal.signal(signal.SIGTERM, original_sigterm)
            except (ValueError, AttributeError):
                pass

        elapsed_seconds = time.perf_counter() - start_time

        # 3. Aggregate run statistics
        all_decisions: list[dict[str, Any]] = []
        for iid in processed_ids:
            all_decisions.extend(get_decisions_for_item(self.conn, iid))

        total_decisions = len(all_decisions)
        cache_hits = sum(1 for d in all_decisions if d.get("from_cache"))
        cache_misses = total_decisions - cache_hits
        cache_hit_rate = (cache_hits / total_decisions * 100.0) if total_decisions > 0 else 0.0

        latencies = [float(d["latency_ms"]) for d in all_decisions if d.get("latency_ms") is not None]
        p50_lat, p95_lat = calculate_percentiles(latencies)

        all_escalations: list[dict[str, Any]] = []
        for iid in processed_ids:
            all_escalations.extend(get_escalations_for_item(self.conn, iid))

        tokens_in = sum(int(e.get("tokens_in") or 0) for e in all_escalations)
        tokens_out = sum(int(e.get("tokens_out") or 0) for e in all_escalations)
        cost_usd = sum(float(e.get("est_cost_usd") or 0.0) for e in all_escalations)

        all_actions: list[dict[str, Any]] = []
        for iid in processed_ids:
            all_actions.extend(get_actions_for_item(self.conn, iid))

        actions_by_tool: dict[str, int] = {}
        for a in all_actions:
            tname = a.get("tool", "unknown")
            actions_by_tool[tname] = actions_by_tool.get(tname, 0) + 1

        return RunSummary(
            total_items=len(processed_ids),
            executed=status_counts.get("executed", 0),
            pending_approval=status_counts.get("pending_approval", 0),
            flagged=status_counts.get("flagged", 0),
            dismissed=status_counts.get("dismissed", 0),
            errors=status_counts.get("error", 0),
            total_decisions=total_decisions,
            cache_hits=cache_hits,
            cache_misses=cache_misses,
            cache_hit_rate_pct=round(cache_hit_rate, 2),
            p50_latency_ms=p50_lat,
            p95_latency_ms=p95_lat,
            bedrock_calls=len(all_escalations),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            total_cost_usd=round(cost_usd, 5),
            duration_seconds=round(elapsed_seconds, 2),
            actions_executed=actions_by_tool,
        )
