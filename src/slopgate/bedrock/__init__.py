"""Amazon Bedrock integration, budget guard, prompts, and escalation logic."""

from slopgate.bedrock.budget import BudgetGuard, BudgetSummary
from slopgate.bedrock.client import (
    BedrockClient,
    BedrockError,
    BedrockResponse,
    BedrockThrottledError,
    GroqClient,
    MockBedrockClient,
    estimate_bedrock_cost,
    get_llm_client,
)
from slopgate.bedrock.escalate import draft_reply, reason_on_ambiguous
from slopgate.bedrock.prompts import (
    DRAFT_REPLY_SYSTEM_PROMPT,
    REASON_ON_AMBIGUOUS_SYSTEM_PROMPT,
    build_draft_reply_prompt,
    build_reason_on_ambiguous_prompt,
    format_untrusted_item_xml,
    sanitize_untrusted_text,
)

__all__ = [
    "DRAFT_REPLY_SYSTEM_PROMPT",
    "REASON_ON_AMBIGUOUS_SYSTEM_PROMPT",
    "BedrockClient",
    "BedrockError",
    "BedrockResponse",
    "BedrockThrottledError",
    "BudgetGuard",
    "BudgetSummary",
    "GroqClient",
    "MockBedrockClient",
    "build_draft_reply_prompt",
    "build_reason_on_ambiguous_prompt",
    "draft_reply",
    "estimate_bedrock_cost",
    "format_untrusted_item_xml",
    "get_llm_client",
    "reason_on_ambiguous",
    "sanitize_untrusted_text",
]
