"""ConfidenceBandHandler: Reusable Strands Decider 2B Decision Pattern.

Tag: #policy
Decoupled, framework-independent decision gating for autonomous agents.
"""

from .bands import Band, classify_choice_band, classify_noul_band, compute_choice_confidence
from .gate import (
    DEFAULT_DESTRUCTIVE_TOOLS,
    ActionKind,
    ConfidenceGate,
    DeciderResult,
    GateVerdict,
    SimplePolicy,
    ToolPolicy,
    load_policy_from_yaml,
)
from .handler import AgentContext, ConfidenceBandHandler

__all__ = [
    "DEFAULT_DESTRUCTIVE_TOOLS",
    "ActionKind",
    "AgentContext",
    "Band",
    "ConfidenceBandHandler",
    "ConfidenceGate",
    "DeciderResult",
    "GateVerdict",
    "SimplePolicy",
    "ToolPolicy",
    "classify_choice_band",
    "classify_noul_band",
    "compute_choice_confidence",
    "load_policy_from_yaml",
]
