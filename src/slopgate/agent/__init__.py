"""Strands Agent runtime, dry-run tools, and ConfidenceBandHandler adapter."""

from slopgate.agent.executor import ExecutionReport, ScriptedExecutor, StepResult
from slopgate.agent.handler import ConfidenceBandHandler, ItemContext
from slopgate.agent.llm_agent import AgentRunSummary, create_escalated_agent, run_escalated_agent
from slopgate.agent.tools import (
    SLOPGATE_TOOLS,
    apply_label,
    close_item,
    compute_idempotency_key,
    flag_for_maintainer,
    post_comment,
    request_info_comment,
    tool_apply_label,
    tool_close_item,
    tool_flag_for_maintainer,
    tool_post_comment,
    tool_request_info_comment,
)

__all__ = [
    "SLOPGATE_TOOLS",
    "AgentRunSummary",
    "ConfidenceBandHandler",
    "ExecutionReport",
    "ItemContext",
    "ScriptedExecutor",
    "StepResult",
    "apply_label",
    "close_item",
    "compute_idempotency_key",
    "create_escalated_agent",
    "flag_for_maintainer",
    "post_comment",
    "request_info_comment",
    "run_escalated_agent",
    "tool_apply_label",
    "tool_close_item",
    "tool_flag_for_maintainer",
    "tool_post_comment",
    "tool_request_info_comment",
]
