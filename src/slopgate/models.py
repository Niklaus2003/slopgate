"""Core domain data models and types for SlopGate.

Follows: Defend What You Ship v2 (04_DATA.md) and architecture.md §5.1.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ItemType = Literal["issue", "pull_request"]
QType = Literal["choice", "noul"]
ItemStatus = Literal[
    "queued",
    "processing",
    "decided",
    "executed",
    "pending_approval",
    "flagged",
    "dismissed",
    "error",
]


class Band(str, Enum):
    """Calibrated confidence bands."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"  # for noul: UNCERTAIN maps to low


class ActionKind(str, Enum):
    """Vocabulary of policy gate actions.

    Severity precedence: DENY > CONFIRM > GUIDE > PROCEED_SOFT > PROCEED.
    """

    PROCEED = "proceed"
    PROCEED_SOFT = "proceed_soft"
    CONFIRM = "confirm"
    GUIDE = "guide"
    DENY = "deny"


class Item(BaseModel):
    """Represents an incoming GitHub issue or pull request."""

    model_config = ConfigDict(extra="ignore")

    repo: str
    number: int
    type: ItemType = "issue"
    title: str = ""
    body: str = ""
    created_at: str = ""
    files: list[str] = Field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    ci_status: str = "unknown"
    author_login: str | None = None  # Excluded from Decider state by default
    raw: dict[str, Any] = Field(default_factory=dict)
    status: ItemStatus = "queued"

    @property
    def id(self) -> str:
        """Composite identifier: repo#number."""
        return f"{self.repo}#{self.number}"


class Facts(BaseModel):
    """Deterministic, code-extracted facts (plain code, no AI)."""

    model_config = ConfigDict(extra="ignore")

    cited_paths_found: tuple[int, int] = (0, 0)  # (found, cited)
    has_code_block: bool = False
    has_repro_heading: bool = False
    template_filled: tuple[int, int] = (0, 0)  # (filled, total)
    links_to_issue: list[int] = Field(default_factory=list)
    ci_status: str = "unknown"
    candidate_duplicate: tuple[int, float] | None = None  # (issue_number, similarity_score)
    contributing_excerpt: str | None = None
    author_history: str | None = None  # Excluded by default unless policy.state.include_author_history=True


class State(BaseModel):
    """Bounded, compact text representation passed to Decider 2B."""

    model_config = ConfigDict(extra="ignore")

    text: str
    hash: str
    approx_tokens: int
    facts: Facts

    @property
    def state_hash(self) -> str:
        return self.hash


class Question(BaseModel):
    """Typed Decider question specification."""

    model_config = ConfigDict(extra="ignore")

    id: str
    qtype: QType
    text: str
    options: tuple[str, ...] = ()  # choice only
    descriptions: dict[str, str] = Field(default_factory=dict)
    applies_to: tuple[ItemType, ...] = ("issue", "pull_request")


class DeciderResult(BaseModel):
    """Raw and calibrated result of a Decider forward pass."""

    model_config = ConfigDict(extra="ignore")

    question_id: str
    qtype: QType
    answer: str | bool  # Winning choice label, or noul bool at 0.5 (do not use bare bool for gating)
    probs: dict[str, float]  # Option -> probability; noul: {"true": p, "false": 1-p}
    confidence: float | None = None  # Normalized confidence for choice; None for noul
    latency_ms: float = 0.0
    model_id: str = ""
    from_cache: bool = False


class GateVerdict(BaseModel):
    """Verdict emitted by the ConfidenceGate for a proposed tool call."""

    model_config = ConfigDict(extra="ignore")

    question_id: str
    band: Band
    action: ActionKind
    reason: str
    is_soft: bool = False


class PlannedToolCall(BaseModel):
    """A proposed tool execution step."""

    model_config = ConfigDict(extra="ignore")

    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None


class ActionPlan(BaseModel):
    """Full resolved plan for an item."""

    model_config = ConfigDict(extra="ignore")

    steps: list[PlannedToolCall] = Field(default_factory=list)
    overall: ActionKind = ActionKind.CONFIRM
    needs_bedrock_draft: bool = False
    needs_bedrock_reasoning: bool = False
    receipt_notes: list[str] = Field(default_factory=list)
    suggested_labels: list[str] = Field(default_factory=list)
    draft_comment: str | None = None
