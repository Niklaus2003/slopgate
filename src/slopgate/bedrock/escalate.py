"""Escalation routines using Amazon Bedrock for drafting replies and reasoning.

Follows: architecture.md §6.7, §11, problem-statement.md §9.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

from slopgate.agent.tools import _build_info_request_comment
from slopgate.bedrock.budget import BudgetGuard
from slopgate.bedrock.client import BedrockClient, BedrockResponse
from slopgate.bedrock.prompts import (
    DRAFT_REPLY_SYSTEM_PROMPT,
    REASON_ON_AMBIGUOUS_SYSTEM_PROMPT,
    build_draft_reply_prompt,
    build_reason_on_ambiguous_prompt,
)
from slopgate.models import Facts, Item
from slopgate.store.db import save_escalation

logger = logging.getLogger(__name__)

FORBIDDEN_TERMS = ["ai-generated", "ai bot", "slop", "hallucinat", "low effort bot", "automated junk"]


def _sanitize_draft(text: str) -> str:
    """Validate and clean generated draft text against safety invariants."""
    text_clean = text.strip()
    text_lower = text_clean.lower()

    # Safety Invariant: Check for forbidden accusatory terms
    for term in FORBIDDEN_TERMS:
        if term in text_lower:
            logger.warning("Bedrock draft contained forbidden term '%s'; falling back to kind template.", term)
            return _build_info_request_comment(
                template_type="general",
                missing_fields=["Minimal reproduction steps", "Expected behavior"],
            )

    # Word count check: cap at 150 words
    words = text_clean.split()
    if len(words) > 150:
        logger.info("Truncating over-long draft from %d words to 120 words.", len(words))
        text_clean = " ".join(words[:120]) + "..."

    return text_clean


def draft_reply(
    item: Item,
    receipt_notes: list[str] | None = None,
    template_hint: str = "",
    client: BedrockClient | None = None,
    budget: BudgetGuard | None = None,
    conn: sqlite3.Connection | None = None,
    item_id: int | None = None,
) -> str:
    """Draft a kind, specific maintainer reply comment using Bedrock or fallback."""
    receipt_notes = receipt_notes or []
    budget_guard = budget or BudgetGuard()
    bedrock_client = client or BedrockClient()

    # 1. Budget Circuit Breaker Check
    if not budget_guard.allow("draft_reply"):
        logger.info("Bedrock budget cap reached; degrading to template comment for %s#%d", item.repo, item.number)
        return _build_info_request_comment(
            template_type=template_hint or "general",
            missing_fields=["Steps to reproduce", "Minimal code snippet"],
        )

    # 2. Construct Prompt and Invoke Bedrock
    prompt = build_draft_reply_prompt(item, receipt_notes, template_hint)
    try:
        response: BedrockResponse = bedrock_client.invoke(
            prompt=prompt,
            system_prompt=DRAFT_REPLY_SYSTEM_PROMPT,
            max_tokens=150,
            temperature=0.3,
        )

        budget_guard.record_usage(
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            cost_usd=response.est_cost_usd,
            purpose="draft_reply",
        )

        # 3. Log Escalation into SQLite
        if conn and item_id and item_id > 0:
            save_escalation(
                conn=conn,
                item_id=item_id,
                purpose="draft_reply",
                bedrock_model=response.model_id,
                tokens_in=response.tokens_in,
                tokens_out=response.tokens_out,
                latency_ms=response.latency_ms,
                est_cost_usd=response.est_cost_usd,
                output_text=response.text,
            )

        return _sanitize_draft(response.text)

    except Exception as err:  # noqa: BLE001
        logger.error("Bedrock draft_reply failed (%s); degrading to template.", err)
        return _build_info_request_comment(
            template_type=template_hint or "general",
            missing_fields=["Steps to reproduce", "Relevant error logs"],
        )


def reason_on_ambiguous(
    item: Item,
    facts: Facts,
    decider_probs: dict[str, float],
    client: BedrockClient | None = None,
    budget: BudgetGuard | None = None,
    conn: sqlite3.Connection | None = None,
    item_id: int | None = None,
) -> dict[str, Any]:
    """Execute LLM reasoning over ambiguous cases with strict JSON validation."""
    budget_guard = budget or BudgetGuard()
    bedrock_client = client or BedrockClient()

    fallback_result = {
        "suggested_label": "needs-triage",
        "rationale": "Ambiguous case routed to maintainer review.",
        "needs_maintainer_review": True,
    }

    # 1. Budget Circuit Breaker Check
    if not budget_guard.allow("reason_on_ambiguous"):
        logger.info("Bedrock budget cap reached; flagging %s#%d for maintainer review without LLM.", item.repo, item.number)
        fallback_result["rationale"] = "Budget cap reached; flagged directly for maintainer review."
        return fallback_result

    # 2. Construct Prompt and Invoke Bedrock
    prompt = build_reason_on_ambiguous_prompt(item, facts, decider_probs)
    try:
        response: BedrockResponse = bedrock_client.invoke(
            prompt=prompt,
            system_prompt=REASON_ON_AMBIGUOUS_SYSTEM_PROMPT,
            max_tokens=150,
            temperature=0.1,
        )

        budget_guard.record_usage(
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            cost_usd=response.est_cost_usd,
            purpose="reason_on_ambiguous",
        )

        # 3. Log Escalation into SQLite
        if conn and item_id and item_id > 0:
            save_escalation(
                conn=conn,
                item_id=item_id,
                purpose="reason_on_ambiguous",
                bedrock_model=response.model_id,
                tokens_in=response.tokens_in,
                tokens_out=response.tokens_out,
                latency_ms=response.latency_ms,
                est_cost_usd=response.est_cost_usd,
                output_text=response.text,
            )

        # 4. Strict JSON Validation (Never leniently parse malformed or injection outputs)
        raw_text = response.text.strip()
        # Strip potential markdown formatting if model accidentally included it
        if raw_text.startswith("```json"):
            raw_text = raw_text.removeprefix("```json")
        if raw_text.startswith("```"):
            raw_text = raw_text.removeprefix("```")
        if raw_text.endswith("```"):
            raw_text = raw_text.removesuffix("```")
        raw_text = raw_text.strip()

        parsed = json.loads(raw_text)
        if not isinstance(parsed, dict) or "suggested_label" not in parsed:
            raise ValueError(f"Missing required 'suggested_label' key in JSON: {raw_text[:100]}")

        parsed["needs_maintainer_review"] = True  # Always enforce maintainer review on ambiguous items
        return parsed

    except Exception as err:  # noqa: BLE001
        logger.warning("Bedrock reasoning failed or returned invalid JSON (%s); flagging for maintainer.", err)
        fallback_result["rationale"] = f"Reasoning failure ({err}); requires maintainer review."
        return fallback_result
