"""Decider Question Cascade and Early-Exit Logic.

Executes Q1 first, evaluates confidence band, and conditionally batches follow-up
noul questions (N1-N5) in a single inference call to exploit state KV prefix reuse.
Follows: architecture.md §6.4, problem-statement.md §7.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from slopgate.config import PolicyConfig
from slopgate.decider.client import DeciderClient
from slopgate.decider.questions import (
    N1_QUESTION,
    N2_QUESTION,
    N3_QUESTION,
    N4_QUESTION,
    N5_QUESTION,
    get_q1_question,
)
from slopgate.models import Band, DeciderResult, Facts, Item, Question, State
from slopgate.policy.bands import classify_choice_band

logger = logging.getLogger(__name__)


def pick_q1(item_type: str) -> Question:
    """Pick canonical Q1 question for issue or pull request."""
    return get_q1_question(item_type)


def extract_duplicate_similarity(candidate_duplicate: Any) -> float | None:
    """Extract float similarity score from facts candidate_duplicate (tuple or str)."""
    if candidate_duplicate is None:
        return None
    if isinstance(candidate_duplicate, (tuple, list)) and len(candidate_duplicate) >= 2:
        try:
            return float(candidate_duplicate[1])
        except (ValueError, TypeError):
            return None
    if isinstance(candidate_duplicate, str):
        if not candidate_duplicate or candidate_duplicate.strip().lower() == "none":
            return None
        match = re.search(r"similarity\s+([0-9.]+)", candidate_duplicate, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
    return None


def select_followups(
    item: Item,
    facts: Facts,
    q1_result: DeciderResult,
    q1_band: Band,
    policy: PolicyConfig,
) -> list[Question]:
    """Select conditional follow-up questions (N1-N5) based on Q1 outcome and facts.

    Implements early-exit rules to conserve CPU time:
    - High-confidence support questions, security reports, low-effort items,
      and feature requests stop early without follow-ups.
    - Bug reports ask N1 (reproduction) and N2 (grounding).
    - PRs ask N2 and N3 (rationale).
    - Items with duplicate candidates >= policy threshold ask N4.
    - Items with CONTRIBUTING facts ask N5.
    """
    answer_str = str(q1_result.answer)
    followups: list[Question] = []

    # 1. Early-exit checks for unambiguous HIGH confidence outcomes
    if q1_band == Band.HIGH and answer_str in (
        "support_question",
        "security_report",
        "low_effort",
        "feature_request",
    ):
        logger.debug(
            "Early exit for item %s#%d: Q1=%s at HIGH confidence",
            item.repo,
            item.number,
            answer_str,
        )
        return []

    # 2. Bug report follow-ups
    if answer_str == "real_bug_report":
        followups.append(N1_QUESTION)
        followups.append(N2_QUESTION)

    # 3. Pull request follow-ups
    elif answer_str == "ready_for_review":
        followups.append(N2_QUESTION)
        if item.type == "pull_request":
            followups.append(N3_QUESTION)

    elif item.type == "pull_request" and answer_str != "low_effort":
        followups.append(N3_QUESTION)

    # 4. If Q1 is uncertain (MEDIUM or LOW) on an issue, collect grounding evidence
    if q1_band in (Band.MEDIUM, Band.LOW) and item.type == "issue":
        if N1_QUESTION not in followups:
            followups.append(N1_QUESTION)
        if N2_QUESTION not in followups:
            followups.append(N2_QUESTION)

    # 5. Duplicate candidate verification (N4)
    sim_score = extract_duplicate_similarity(facts.candidate_duplicate)
    if sim_score is not None and sim_score >= policy.duplicate.similarity_min:
        followups.append(N4_QUESTION)

    # 6. Contributing guideline verification (N5)
    contrib = facts.contributing_excerpt or getattr(facts, "contributing_summary", None) or ""
    if contrib and str(contrib).strip().lower() != "none":
        followups.append(N5_QUESTION)

    # 7. Deduplicate while preserving order and verifying applies_to
    deduped: list[Question] = []
    seen: set[str] = set()
    for q in followups:
        if q.id not in seen and item.type in q.applies_to:
            seen.add(q.id)
            deduped.append(q)

    return deduped


def run_cascade(
    item: Item,
    state: State,
    decider: DeciderClient,
    policy: PolicyConfig,
) -> list[DeciderResult]:
    """Execute Decider Q1 -> conditional follow-ups in at most two calls.

    1. Evaluates Q1 choice question.
    2. Determines Q1 confidence band.
    3. If follow-ups needed, batches all of them in a SINGLE ask() call,
       allowing InProcessDecider to reuse the state KV prefix cache.
    4. Returns combined DeciderResult list.
    """
    # Step 1: Pick and ask Q1
    q1 = pick_q1(item.type)
    q1_results = decider.ask(state, [q1])
    if not q1_results:
        raise RuntimeError(f"Decider returned empty response for Q1 on {item.repo}#{item.number}")

    r1 = q1_results[0]
    q1_band = classify_choice_band(
        r1.confidence or 0.0,
        high_at_least=policy.bands.choice.high_at_least,
        medium_at_least=policy.bands.choice.medium_at_least,
    )

    # Step 2: Select conditional follow-ups
    followups = select_followups(item, state.facts, r1, q1_band, policy)

    # Step 3: Batch follow-ups or early exit
    if not followups:
        return [r1]

    # One call evaluates all follow-ups against the state KV cache
    followup_results = decider.ask(state, followups)
    return [r1] + followup_results
