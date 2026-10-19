"""ConfidenceGate (Standalone Pattern Component).

Evaluates proposed agent tool calls against Decider results and policy rules.
Emits typed GateVerdict: Proceed, Confirm, Guide, Deny.

Enforces hardcoded safety defaults in code:
- Destructive tools (e.g. close, delete, drop) can never auto-proceed without confirmation.
- Unlisted tools default to confirmation.

Zero external framework dependencies outside standard library and optional pyyaml.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

try:
    from patterns.confidence_band_handler.bands import (
        Band,
        classify_choice_band,
        classify_noul_band,
        compute_choice_confidence,
    )
except ImportError:
    try:
        from .bands import (
            Band,
            classify_choice_band,
            classify_noul_band,
            compute_choice_confidence,
        )
    except ImportError:
        from bands import (  # type: ignore[no-redef]
            Band,
            classify_choice_band,
            classify_noul_band,
            compute_choice_confidence,
        )


class ActionKind(str, Enum):
    """Four-way permission actions."""

    PROCEED = "proceed"
    CONFIRM = "confirm"
    GUIDE = "guide"
    DENY = "deny"


@dataclass(frozen=True)
class DeciderResult:
    """Standardized decision input."""

    question_id: str
    qtype: str  # choice | noul
    answer: str | bool
    probs: dict[str, float]
    confidence: float | None = None


@dataclass(frozen=True)
class GateVerdict:
    """Verdict emitted by ConfidenceGate."""

    question_id: str
    band: Band
    action: ActionKind
    reason: str
    is_soft: bool = False


@dataclass
class ToolPolicy:
    """Policy configuration for a single tool."""

    requires: list[str] = field(default_factory=list)
    always: str | None = None


DEFAULT_DESTRUCTIVE_TOOLS: set[str] = {
    "close_item",
    "delete_database",
    "drop_table",
    "refund_unlimited",
    "delete_record",
    "delete_user",
    "wipe_disk",
    "purge_data",
}


@dataclass
class SimplePolicy:
    """Minimal policy configuration container."""

    high_at_least: float = 0.80
    medium_at_least: float = 0.50
    true_at_least: float = 0.85
    false_at_most: float = 0.15
    tools_gated: dict[str, ToolPolicy] = field(default_factory=dict)
    routing: dict[str, dict[str, str]] = field(default_factory=dict)
    destructive_tools: set[str] = field(default_factory=lambda: set(DEFAULT_DESTRUCTIVE_TOOLS))


def load_policy_from_yaml(path: str | Path) -> SimplePolicy:
    """Load SimplePolicy from YAML file if PyYAML is available."""
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(f"Policy YAML not found: {target}")

    try:
        import yaml
    except ImportError as exc:
        raise ImportError(
            "PyYAML is required to parse policy YAML files. "
            "Install with 'pip install pyyaml' or instantiate SimplePolicy directly."
        ) from exc

    raw: dict[str, Any] = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    bands_raw = raw.get("bands", {})
    choice_raw = bands_raw.get("choice", {})
    noul_raw = bands_raw.get("noul", {})

    tools_gated: dict[str, ToolPolicy] = {}
    for tool_name, tcfg in raw.get("tools_gated", {}).items():
        if isinstance(tcfg, dict):
            tools_gated[tool_name] = ToolPolicy(
                requires=tcfg.get("requires", []),
                always=tcfg.get("always"),
            )
        else:
            tools_gated[tool_name] = ToolPolicy()

    routing: dict[str, dict[str, str]] = raw.get("routing", {})
    destructive_list = raw.get("destructive_tools", None)
    destructive = set(destructive_list) if destructive_list is not None else set(DEFAULT_DESTRUCTIVE_TOOLS)

    return SimplePolicy(
        high_at_least=float(choice_raw.get("high_at_least", 0.80)),
        medium_at_least=float(choice_raw.get("medium_at_least", 0.50)),
        true_at_least=float(noul_raw.get("true_at_least", 0.85)),
        false_at_most=float(noul_raw.get("false_at_most", 0.15)),
        tools_gated=tools_gated,
        routing=routing,
        destructive_tools=destructive,
    )


class ConfidenceGate:
    """Core policy gate evaluating proposed tool actions against decider outputs."""

    DEFAULT_DESTRUCTIVE_TOOLS = DEFAULT_DESTRUCTIVE_TOOLS

    def __init__(self, policy: SimplePolicy | None = None) -> None:
        self.policy = policy or SimplePolicy()

    def is_destructive(self, tool_name: str, policy: SimplePolicy | None = None) -> bool:
        """Check if a tool is flagged as destructive."""
        active_policy = policy or self.policy
        return (
            tool_name in self.DEFAULT_DESTRUCTIVE_TOOLS
            or tool_name in active_policy.destructive_tools
            or tool_name.startswith(("delete_", "drop_", "wipe_"))
        )

    def evaluate(
        self,
        tool_name: str,
        decisions: list[DeciderResult],
        policy: SimplePolicy | None = None,
    ) -> GateVerdict:
        """Evaluate whether a proposed tool call may execute."""
        active_policy = policy or self.policy

        # Safety Invariant: Destructive actions always require human confirmation
        if self.is_destructive(tool_name, active_policy):
            return GateVerdict(
                question_id="SAFETY_INVARIANT",
                band=Band.HIGH,
                action=ActionKind.CONFIRM,
                reason=f"Action '{tool_name}' is destructive and requires human confirmation.",
            )

        # Safety Invariant: Unlisted tools default to confirm
        if tool_name not in active_policy.tools_gated:
            return GateVerdict(
                question_id="SAFETY_UNLISTED_TOOL",
                band=Band.MEDIUM,
                action=ActionKind.CONFIRM,
                reason=f"Tool '{tool_name}' is not in policy.tools_gated; defaulting to confirm.",
            )

        tool_gate = active_policy.tools_gated[tool_name]
        if tool_gate.always:
            return GateVerdict(
                question_id="TOOL_POLICY_ALWAYS",
                band=Band.HIGH,
                action=ActionKind(tool_gate.always.lower()),
                reason=f"Tool '{tool_name}' is statically configured as always '{tool_gate.always}'.",
            )

        decisions_by_id = {d.question_id: d for d in decisions}

        # Check required decisions
        for req_q in tool_gate.requires:
            if req_q not in decisions_by_id and not any(qid.startswith(req_q) for qid in decisions_by_id):
                return GateVerdict(
                    question_id=req_q,
                    band=Band.LOW,
                    action=ActionKind.CONFIRM,
                    reason=f"Missing required decision '{req_q}' for tool '{tool_name}'.",
                )

        # Determine primary decision: check required question(s) or default to Q1 or first available
        primary_q_id = tool_gate.requires[0] if tool_gate.requires else "Q1"
        target_res = decisions_by_id.get(primary_q_id) or next(
            (
                d
                for qid, d in decisions_by_id.items()
                if qid == primary_q_id
                or qid == "Q1"
                or qid.startswith("Q1")
                or (tool_gate.requires and any(qid.startswith(req) for req in tool_gate.requires))
            ),
            None,
        )

        if not target_res:
            target_res = decisions[0] if decisions else None

        if not target_res:
            return GateVerdict(
                question_id="MISSING_DECISION",
                band=Band.LOW,
                action=ActionKind.CONFIRM,
                reason=f"No decision available to evaluate tool '{tool_name}'.",
            )

        # Handle binary noul questions
        if target_res.qtype == "noul":
            probs = target_res.probs or {}
            p_true = probs.get("True", probs.get("true", 0.5))
            band, polarity = classify_noul_band(
                p_true=p_true,
                true_at_least=active_policy.true_at_least,
                false_at_most=active_policy.false_at_most,
            )
            answer_key = "true" if polarity is True else ("false" if polarity is False else "uncertain")
            route_config = active_policy.routing.get(answer_key, {})
            target_action_str = route_config.get(band.value)
            if not target_action_str:
                target_action = ActionKind.PROCEED if (band == Band.HIGH and polarity is True) else ActionKind.CONFIRM
            else:
                target_action = ActionKind(target_action_str.lower())

            return GateVerdict(
                question_id=target_res.question_id,
                band=band,
                action=target_action,
                reason=(
                    f"Binary decision '{target_res.question_id}' (P(True)={p_true:.2f}, band={band.value}) "
                    f"routes to {target_action.value}."
                ),
            )

        # Handle categorical choice questions
        conf = target_res.confidence
        if conf is None and target_res.probs:
            conf = compute_choice_confidence(target_res.probs)
        conf = conf or 0.0

        band = classify_choice_band(
            confidence=conf,
            high_at_least=active_policy.high_at_least,
            medium_at_least=active_policy.medium_at_least,
        )

        answer_key = str(target_res.answer)
        route_config = active_policy.routing.get(answer_key, {})
        target_action_str = route_config.get(band.value)

        if not target_action_str:
            target_action = ActionKind.CONFIRM if band != Band.HIGH else ActionKind.PROCEED
        else:
            target_action = ActionKind(target_action_str.lower())

        return GateVerdict(
            question_id=target_res.question_id,
            band=band,
            action=target_action,
            reason=(
                f"Decider classification '{answer_key}' with confidence {conf:.2f} "
                f"(band: {band.value}) routes to {target_action.value}."
            ),
        )
