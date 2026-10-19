"""ConfidenceBandHandler (Standalone Reusable Adapter).

InterventionHandler adapter for Strands Agents SDK.
Intercepts tool executions, queries ConfidenceGate, and returns typed intervention actions:
- Proceed
- Confirm
- Guide
- Deny

Zero application imports outside strands.interventions and the pattern's own gate.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from strands.interventions import Confirm, Deny, Guide, InterventionHandler, Proceed

try:
    from patterns.confidence_band_handler.gate import (
        ActionKind,
        ConfidenceGate,
        DeciderResult,
        GateVerdict,
        SimplePolicy,
    )
except ImportError:
    try:
        from .gate import ActionKind, ConfidenceGate, DeciderResult, GateVerdict, SimplePolicy
    except ImportError:
        from gate import ActionKind, ConfidenceGate, DeciderResult, GateVerdict, SimplePolicy  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


@dataclass
class AgentContext:
    """Invocation context providing current item and Decider results."""

    identifier: str
    results: list[DeciderResult]
    extra: dict[str, Any] = field(default_factory=dict)
    audit_notes: list[str] = field(default_factory=list)


class ConfidenceBandHandler(InterventionHandler):
    """Strands intervention handler translating confidence bands into execution actions."""

    name: str = "confidence-band-handler"

    def __init__(
        self,
        gate: ConfidenceGate,
        context_provider: Callable[[], AgentContext],
        policy: SimplePolicy | None = None,
    ) -> None:
        super().__init__()
        self.gate = gate
        self.context_provider = context_provider
        self.policy = policy

    def _extract_tool_name(self, event: Any) -> str:
        """Extract tool name from BeforeToolCallEvent or duck-typed event."""
        if hasattr(event, "tool_use") and isinstance(event.tool_use, dict):
            return str(event.tool_use.get("name", "unknown"))
        if hasattr(event, "selected_tool") and event.selected_tool is not None:
            return getattr(event.selected_tool, "tool_name", "unknown")
        if hasattr(event, "tool_name"):
            return str(event.tool_name)
        return "unknown"

    def before_tool_call(self, event: Any, **kwargs: Any) -> Proceed | Confirm | Guide | Deny:
        """Intercept tool call and evaluate against confidence gate."""
        tool_name = self._extract_tool_name(event)
        ctx = self.context_provider()

        verdict: GateVerdict = self.gate.evaluate(
            tool_name=tool_name,
            decisions=ctx.results,
            policy=self.policy,
        )

        note = f"Tool '{tool_name}' for [{ctx.identifier}]: verdict={verdict.action.value} (band={verdict.band.value})"
        ctx.audit_notes.append(note)
        logger.info(note)

        if verdict.action == ActionKind.PROCEED:
            return Proceed(reason=verdict.reason)

        if verdict.action == ActionKind.CONFIRM:
            return Confirm(
                prompt=f"Human confirmation required for tool '{tool_name}': {verdict.reason}",
                reason=verdict.reason,
            )

        if verdict.action == ActionKind.GUIDE:
            return Guide(
                feedback=f"Policy guidance for tool '{tool_name}': {verdict.reason}",
                reason=verdict.reason,
            )

        return Deny(reason=f"Policy violation: Tool '{tool_name}' denied. {verdict.reason}")
