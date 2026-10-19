"""ConfidenceBandHandler: Strands Agents InterventionHandler adapter.

Interposes on Strands agent tool executions, delegating policy evaluation
to the framework-free ConfidenceGate. Maps GateVerdict into Strands intervention
actions: Proceed, Confirm, Guide, Deny.

Follows: architecture.md §6.6, docs/defense/03_FLOW.md.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from strands.interventions import Confirm, Deny, Guide, InterventionHandler, Proceed

from slopgate.config import PolicyConfig
from slopgate.models import ActionKind, DeciderResult, GateVerdict, Item
from slopgate.policy.gate import ConfidenceGate

logger = logging.getLogger(__name__)


@dataclass
class ItemContext:
    """Per-invocation context passed to ConfidenceBandHandler."""

    item: Item
    results: list[DeciderResult]
    dry_run: bool = True
    audit_trail: list[dict[str, Any]] = field(default_factory=list)
    receipt_notes: list[str] = field(default_factory=list)


class ConfidenceBandHandler(InterventionHandler):
    """Strands Agents intervention handler wrapping ConfidenceGate.

    Translates mathematical confidence bands into agent execution permissions:
    - PROCEED / PROCEED_SOFT -> Proceed()
    - CONFIRM                -> Confirm()
    - GUIDE                  -> Guide()
    - DENY                   -> Deny()
    """

    name: str = "confidence-band-handler"

    def __init__(
        self,
        gate: ConfidenceGate,
        context_provider: Callable[[], ItemContext],
        policy: PolicyConfig,
    ) -> None:
        super().__init__()
        self.gate = gate
        self.context_provider = context_provider
        self.policy = policy

    def _extract_tool_name(self, event: Any) -> str:
        """Extract tool name from BeforeToolCallEvent or mock event."""
        if hasattr(event, "tool_use") and isinstance(event.tool_use, dict):
            return str(event.tool_use.get("name", "unknown"))
        if hasattr(event, "selected_tool") and event.selected_tool is not None:
            return getattr(event.selected_tool, "tool_name", "unknown")
        if hasattr(event, "tool_name"):
            return str(event.tool_name)
        return "unknown"

    def before_tool_call(self, event: Any, **kwargs: Any) -> Proceed | Confirm | Guide | Deny:
        """Evaluate policy gate before the agent executes any tool."""
        tool_name = self._extract_tool_name(event)
        ctx = self.context_provider()

        verdict: GateVerdict = self.gate.evaluate(
            tool_name=tool_name,
            decisions=ctx.results,
            policy=self.policy,
        )

        logger.info(
            "ConfidenceBandHandler evaluated tool '%s' for %s#%d: action=%s, band=%s, reason=%s",
            tool_name,
            ctx.item.repo,
            ctx.item.number,
            verdict.action.value,
            verdict.band.value,
            verdict.reason,
        )

        # Record audit entry in context
        ctx.audit_trail.append(
            {
                "tool": tool_name,
                "action": verdict.action.value,
                "band": verdict.band.value,
                "reason": verdict.reason,
                "is_soft": verdict.is_soft,
            }
        )
        ctx.receipt_notes.append(f"Gate {verdict.action.value.upper()} for {tool_name}: {verdict.reason}")

        # Map GateVerdict to Strands intervention action
        if verdict.action in (ActionKind.PROCEED, ActionKind.PROCEED_SOFT):
            return Proceed(reason=verdict.reason)

        if verdict.action == ActionKind.CONFIRM:
            return Confirm(
                prompt=f"Maintainer confirmation required for '{tool_name}': {verdict.reason}",
                reason=verdict.reason,
            )

        if verdict.action == ActionKind.GUIDE:
            return Guide(
                feedback=f"Policy guidance for '{tool_name}': {verdict.reason}",
                reason=verdict.reason,
            )

        # Fallthrough to DENY
        return Deny(reason=f"Policy violation: '{tool_name}' is denied. {verdict.reason}")
