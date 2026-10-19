"""Pure Bedrock LLM classification baseline runner for SlopGate.

Evaluates a sample of items through a single-turn Bedrock model call
(e.g., amazon.nova-micro-v1:0) to benchmark against SlopGate's hybrid
Decider 2B local CPU architecture for cost, latency, and accuracy.
Follows: implementation-plan.md Phase 8 Step 5, architecture.md §7.3.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3

    from slopgate.bedrock.budget import BudgetGuard
    from slopgate.bedrock.client import BedrockClient
    from slopgate.models import Item

from slopgate.bedrock.prompts import sanitize_untrusted_text
from slopgate.decider.questions import Q1_ISSUE_OPTIONS, Q1_PR_OPTIONS
from slopgate.store.db import get_ground_truth, save_escalation, save_item

logger = logging.getLogger(__name__)

BASELINE_SYSTEM_PROMPT = """You are an automated GitHub triage assistant.
Classify the given contribution into exactly one category.

For issues, choose one of:
- real_bug_report: reports a specific problem with enough detail to investigate
- feature_request: asks for new behavior
- support_question: asks how to use the software
- likely_duplicate: repeats an existing known problem
- security_report: describes a possible vulnerability
- low_effort: lacks concrete detail, reproduction, or a clear purpose

For pull requests, choose one of:
- ready_for_review: clear purpose, scoped change, follows guidelines
- needs_work: reasonable purpose but missing explanation or tests
- out_of_scope: change unrelated to project goals or accepted issue
- low_effort: unclear purpose, trivial churn, or no explanation

Respond in strict JSON with no markdown wrapping:
{"label": "<category>", "reason": "<one sentence justification>"}
"""


@dataclass
class BaselineItemResult:
    item_id: int
    repo: str
    number: int
    predicted_label: str
    ground_truth_label: str | None
    correct: bool | None
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: float


@dataclass
class BaselineResult:
    total_items: int = 0
    correct_count: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_cost_usd: float = 0.0
    latencies_ms: list[float] = field(default_factory=list)
    items: list[BaselineItemResult] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        evaluated = sum(1 for item in self.items if item.correct is not None)
        if evaluated == 0:
            return 0.0
        return self.correct_count / evaluated

    @property
    def cost_per_item_usd(self) -> float:
        if self.total_items == 0:
            return 0.0
        return self.total_cost_usd / self.total_items

    @property
    def projected_cost_per_1000_usd(self) -> float:
        return self.cost_per_item_usd * 1000.0


def run_bedrock_baseline(
    items: list[Item],
    conn: sqlite3.Connection,
    bedrock_client: BedrockClient,
    budget_guard: BudgetGuard,
    limit: int = 25,
) -> BaselineResult:
    """Run baseline classification on items using a small Bedrock model."""
    result = BaselineResult()
    selected_items = items[:limit]

    for item in selected_items:
        # Check budget allowance
        if not budget_guard.allow("baseline"):
            logger.warning("Bedrock budget reached during baseline run; stopping early.")
            break

        item_id = save_item(conn, item)
        valid_options = Q1_PR_OPTIONS if item.type == "pull_request" else Q1_ISSUE_OPTIONS

        # Sanitize untrusted user text
        safe_title = sanitize_untrusted_text(item.title or "")
        safe_body = sanitize_untrusted_text(item.body or "")[:800]

        user_content = (
            f"Contribution Type: {item.type.upper()}\n"
            f"<untrusted_item>\n"
            f"Title: {safe_title}\n\n"
            f"Body:\n{safe_body}\n"
            f"</untrusted_item>\n\n"
            f"Allowed categories: {', '.join(valid_options)}"
        )

        try:
            response = bedrock_client.invoke(
                prompt=user_content,
                system_prompt=BASELINE_SYSTEM_PROMPT,
                max_tokens=100,
                temperature=0.0,
            )

            budget_guard.record_usage(
                tokens_in=response.tokens_in,
                tokens_out=response.tokens_out,
                cost_usd=response.est_cost_usd,
                purpose="baseline",
            )

            # Save escalation record in DB
            save_escalation(
                conn=conn,
                item_id=item_id,
                purpose="baseline",
                bedrock_model=response.model_id,
                tokens_in=response.tokens_in,
                tokens_out=response.tokens_out,
                latency_ms=response.latency_ms,
                est_cost_usd=response.est_cost_usd,
                output_text=response.text,
            )

            # Parse response JSON
            pred_label = "low_effort"
            clean_text = response.text.strip()
            if "```" in clean_text:
                m = re.search(r"\{.*?\}", clean_text, re.DOTALL)
                clean_text = m.group(0) if m else clean_text

            try:
                data = json.loads(clean_text)
                parsed = data.get("label", "").strip().lower()
                if parsed in valid_options:
                    pred_label = parsed
            except (json.JSONDecodeError, KeyError, ValueError):
                logger.warning("Could not parse Bedrock baseline JSON: %s", clean_text[:100])

            # Check correctness against ground truth if present
            gt_row = get_ground_truth(conn, item_id)
            gt_label = gt_row["label"] if gt_row else None
            is_correct = (pred_label == gt_label) if gt_label else None
            if is_correct:
                result.correct_count += 1

            result.total_items += 1
            result.total_tokens_in += response.tokens_in
            result.total_tokens_out += response.tokens_out
            result.total_cost_usd += response.est_cost_usd
            result.latencies_ms.append(response.latency_ms)

            result.items.append(
                BaselineItemResult(
                    item_id=item_id,
                    repo=item.repo,
                    number=item.number,
                    predicted_label=pred_label,
                    ground_truth_label=gt_label,
                    correct=is_correct,
                    tokens_in=response.tokens_in,
                    tokens_out=response.tokens_out,
                    cost_usd=response.est_cost_usd,
                    latency_ms=response.latency_ms,
                )
            )

        except (RuntimeError, ValueError, KeyError, TimeoutError, OSError) as err:
            logger.error("Bedrock baseline call failed on item %s#%d: %s", item.repo, item.number, err)

    return result
