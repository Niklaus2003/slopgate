"""ScriptedExecutor for routine triage plans.

Executes ActionPlan steps when overall policy verdict is PROCEED or PROCEED_SOFT.
Explicitly checks ConfidenceGate before executing each tool step.
If any step evaluates to CONFIRM (such as close_item), it automatically diverts
the plan to the pending_approvals table and marks the item as pending_approval.

Follows: architecture.md §6.6, docs/defense/03_FLOW.md.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from slopgate.agent.tools import (
    apply_label,
    close_item,
    compute_idempotency_key,
    flag_for_maintainer,
    post_comment,
    request_info_comment,
)
from slopgate.config import PolicyConfig
from slopgate.ingest.github import GitHubClient
from slopgate.models import (
    ActionKind,
    ActionPlan,
    DeciderResult,
    GateVerdict,
    Item,
    PlannedToolCall,
)
from slopgate.policy.gate import ConfidenceGate
from slopgate.store.db import (
    save_pending_approval,
    update_item_status,
)

logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    """Outcome of a single planned tool step execution."""

    tool_name: str
    verdict: GateVerdict
    status: str  # executed | simulated | skipped | pending_approval | denied | error
    details: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None


@dataclass
class ExecutionReport:
    """Consolidated report of an ActionPlan execution."""

    item_repo: str
    item_number: int
    overall_status: str  # executed | pending_approval | denied | partially_executed | flagged
    steps: list[StepResult] = field(default_factory=list)
    pending_approval_id: int | None = None
    notes: list[str] = field(default_factory=list)


class ScriptedExecutor:
    """Executes routine triage plans in dry-run or live mode."""

    def __init__(
        self,
        gate: ConfidenceGate,
        policy: PolicyConfig,
        github_client: GitHubClient | None = None,
    ) -> None:
        self.gate = gate
        self.policy = policy
        self.github_client = github_client

    def _execute_single_tool(
        self,
        step: PlannedToolCall,
        item: Item,
        conn: sqlite3.Connection | None = None,
        item_id: int | None = None,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Dispatch a single planned tool call to its tools.py implementation."""
        tool_name = step.tool_name
        args = step.args

        if tool_name == "apply_label":
            return apply_label(
                repo=item.repo,
                number=item.number,
                label=args["label"],
                dry_run=dry_run,
                conn=conn,
                item_id=item_id,
                github_client=self.github_client,
            )

        if tool_name == "post_comment":
            return post_comment(
                repo=item.repo,
                number=item.number,
                body=args["body"],
                dry_run=dry_run,
                conn=conn,
                item_id=item_id,
                github_client=self.github_client,
            )

        if tool_name == "request_info_comment":
            return request_info_comment(
                repo=item.repo,
                number=item.number,
                template_type=args.get("template_type", "general"),
                missing_fields=args.get("missing_fields"),
                dry_run=dry_run,
                conn=conn,
                item_id=item_id,
                github_client=self.github_client,
            )

        if tool_name == "flag_for_maintainer":
            return flag_for_maintainer(
                repo=item.repo,
                number=item.number,
                reason=args.get("reason", "Flagged for maintainer"),
                suggested_action=args.get("suggested_action", "review"),
                dry_run=dry_run,
                conn=conn,
                item_id=item_id,
            )

        if tool_name == "close_item":
            # Note: This is only reachable if explicitly called with verified approval
            return close_item(
                repo=item.repo,
                number=item.number,
                reason=args.get("reason", "Closed by maintainer approval"),
                dry_run=dry_run,
                conn=conn,
                item_id=item_id,
                github_client=self.github_client,
            )

        raise ValueError(f"Unknown tool name: '{tool_name}'")

    def execute_plan(
        self,
        item: Item,
        plan: ActionPlan,
        results: list[DeciderResult],
        conn: sqlite3.Connection | None = None,
        item_id: int | None = None,
        dry_run: bool = True,
    ) -> ExecutionReport:
        """Execute all steps in an ActionPlan with gate verification before every tool."""
        report = ExecutionReport(
            item_repo=item.repo,
            item_number=item.number,
            overall_status="executed",
            notes=list(plan.receipt_notes),
        )

        for step in plan.steps:
            # 1. Gate evaluation before EACH tool execution
            verdict = self.gate.evaluate(
                tool_name=step.tool_name,
                decisions=results,
                policy=self.policy,
            )

            idempotency_key = step.idempotency_key or compute_idempotency_key(
                step.tool_name, item.repo, item.number, step.args
            )

            # 2. Handle CONFIRM (divert to pending_approvals, NEVER auto-execute)
            if verdict.action == ActionKind.CONFIRM:
                logger.info(
                    "Step '%s' requires maintainer confirmation: %s. Diverting to pending_approvals.",
                    step.tool_name,
                    verdict.reason,
                )
                pending_id = None
                if conn and item_id and item_id > 0:
                    pending_id = save_pending_approval(
                        conn=conn,
                        item_id=item_id,
                        proposed_plan=plan.model_dump(),
                        receipt_md=f"Tool '{step.tool_name}' requires human confirmation: {verdict.reason}",
                    )
                    update_item_status(conn, item_id, "pending_approval")

                report.steps.append(
                    StepResult(
                        tool_name=step.tool_name,
                        verdict=verdict,
                        status="pending_approval",
                        details={"reason": verdict.reason},
                        idempotency_key=idempotency_key,
                    )
                )
                report.overall_status = "pending_approval"
                report.pending_approval_id = pending_id
                # Stop further automated execution
                return report

            # 3. Handle DENY (block execution)
            if verdict.action == ActionKind.DENY:
                logger.warning(
                    "Step '%s' denied by policy: %s. Execution blocked.",
                    step.tool_name,
                    verdict.reason,
                )
                report.steps.append(
                    StepResult(
                        tool_name=step.tool_name,
                        verdict=verdict,
                        status="denied",
                        details={"reason": verdict.reason},
                        idempotency_key=idempotency_key,
                    )
                )
                report.overall_status = "denied"
                if conn and item_id and item_id > 0:
                    update_item_status(conn, item_id, "flagged")
                return report

            # 4. Handle GUIDE (route to maintainer flag if unexpected in scripted path)
            if verdict.action == ActionKind.GUIDE:
                logger.info("Step '%s' guided by policy: %s", step.tool_name, verdict.reason)
                flag_res = flag_for_maintainer(
                    repo=item.repo,
                    number=item.number,
                    reason=f"Policy guide: {verdict.reason}",
                    suggested_action="review",
                    dry_run=dry_run,
                    conn=conn,
                    item_id=item_id,
                )
                report.steps.append(
                    StepResult(
                        tool_name="flag_for_maintainer",
                        verdict=verdict,
                        status="guided",
                        details=flag_res,
                        idempotency_key=idempotency_key,
                    )
                )
                report.overall_status = "flagged"
                if conn and item_id and item_id > 0:
                    update_item_status(conn, item_id, "flagged")
                return report

            # 5. Handle PROCEED and PROCEED_SOFT (execute tool safely)
            try:
                tool_outcome = self._execute_single_tool(
                    step=step,
                    item=item,
                    conn=conn,
                    item_id=item_id,
                    dry_run=dry_run,
                )
                report.steps.append(
                    StepResult(
                        tool_name=step.tool_name,
                        verdict=verdict,
                        status=tool_outcome.get("status", "executed"),
                        details=tool_outcome,
                        idempotency_key=idempotency_key,
                    )
                )
            except Exception as tool_err:  # noqa: BLE001 - tool execution error is captured in report, not crash worker
                logger.error("Error executing tool '%s': %s", step.tool_name, tool_err)
                report.steps.append(
                    StepResult(
                        tool_name=step.tool_name,
                        verdict=verdict,
                        status="error",
                        details={"error": str(tool_err)},
                        idempotency_key=idempotency_key,
                    )
                )
                report.overall_status = "error"
                if conn and item_id and item_id > 0:
                    update_item_status(conn, item_id, "error")
                return report

        # Update item status in database if complete
        if conn and item_id and item_id > 0:
            update_item_status(conn, item_id, "executed")

        return report
