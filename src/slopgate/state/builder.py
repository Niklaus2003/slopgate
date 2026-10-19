"""Compact state string builder for Strands Decider 2B.

Enforces <= 450 token cap, deterministic fact inclusion, strict truncation order,
and stable SHA256 hashing.
Follows: problem-statement.md §6.1, architecture.md §6.2.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Sequence

from slopgate.config import PolicyConfig
from slopgate.models import Facts, Item, State
from slopgate.state.facts import extract_all_facts
from slopgate.state.repo_index import RepoIndex

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "v1"


def estimate_tokens(text: str) -> int:
    """Conservative token count estimation on CPU (1 token ~= 4 chars or 0.75 words)."""
    if not text:
        return 0
    char_estimate = len(text) // 4
    word_estimate = int(len(text.split()) * 1.33)
    return max(char_estimate, word_estimate)


def _render_facts(facts: Facts) -> str:
    """Format facts into state text."""
    lines = ["[FACTS]"]

    # cited_paths_found
    found, cited = facts.cited_paths_found
    if cited > 0:
        lines.append(f"- cited_paths_found: {found} of {cited}")
    else:
        lines.append("- cited_paths_found: 0 of 0")

    # has_code_block
    lines.append(f"- has_code_block: {'yes' if facts.has_code_block else 'no'}")

    # has_repro_heading
    lines.append(f"- has_repro_heading: {'yes' if facts.has_repro_heading else 'no'}")

    # template_sections_filled
    t_filled, t_total = facts.template_filled
    lines.append(f"- template_sections_filled: {t_filled} of {t_total}")

    # links_to_issue
    if facts.links_to_issue:
        links_str = ", ".join(f"#{num}" for num in facts.links_to_issue)
        lines.append(f"- links_to_issue: {links_str}")
    else:
        lines.append("- links_to_issue: none")

    # ci_status
    lines.append(f"- ci_status: {facts.ci_status}")

    # candidate_duplicate
    if facts.candidate_duplicate:
        dup_num, dup_sim = facts.candidate_duplicate
        lines.append(f"- candidate_duplicate: #{dup_num} (similarity {dup_sim:.2f})")
    else:
        lines.append("- candidate_duplicate: none")

    # contributing_summary
    if facts.contributing_excerpt:
        lines.append(f"- contributing_summary: {facts.contributing_excerpt}")

    # author_history (only if explicitly enabled)
    if facts.author_history:
        lines.append(f"- author_history: {facts.author_history}")

    return "\n".join(lines)


def build_state(
    item: Item,
    policy: PolicyConfig | None = None,
    repo_index: RepoIndex | None = None,
    candidates: Sequence[Item] | None = None,
    schema_version: str = SCHEMA_VERSION,
) -> State:
    """Build compact, bounded state for Strands Decider 2B.

    Truncation Order (when exceeding token cap):
      1. Truncate body text.
      2. Truncate changed files list and diff summary.
      3. NEVER truncate facts.
    """
    pol = policy or PolicyConfig()
    max_tokens = pol.state.max_tokens
    max_body_chars = pol.state.body_chars
    include_author = pol.state.include_author_history

    # Extract deterministic facts
    facts = extract_all_facts(
        item=item,
        repo_index=repo_index,
        candidates=candidates,
        similarity_min=pol.duplicate.similarity_min,
        include_author_history=include_author,
    )

    facts_text = _render_facts(facts)

    # Whitespace collapse body up to max_body_chars
    raw_body = item.body or ""
    collapsed_body = re.sub(r"[ \t]+", " ", raw_body)
    # Collapse multiple consecutive blank lines
    collapsed_body = re.sub(r"\n\s*\n+", "\n\n", collapsed_body).strip()
    if len(collapsed_body) > max_body_chars:
        body_text = collapsed_body[:max_body_chars] + "..."
    else:
        body_text = collapsed_body

    # Format PR files and diff summary
    files_line = ""
    diff_line = ""
    if item.type == "pull_request":
        if item.files:
            file_sample = item.files[:10]
            files_line = f"\n[FILES] {len(item.files)} changed; {', '.join(file_sample)}"
        if item.additions or item.deletions:
            diff_line = f"\n[DIFF] +{item.additions} -{item.deletions}"

    # Iterative assembly with token enforcement
    def assemble(current_body: str, include_files: bool, include_diff: bool) -> str:
        parts = [
            f"[TYPE] {item.type}",
            f"[TITLE] {item.title}",
            f"[BODY] {current_body}",
        ]
        if include_files and files_line:
            parts.append(files_line.strip())
        if include_diff and diff_line:
            parts.append(diff_line.strip())
        parts.append(facts_text)
        return "\n".join(parts)

    state_text = assemble(body_text, include_files=True, include_diff=True)
    tokens = estimate_tokens(state_text)

    # Step 1: Truncate body if over budget
    if tokens > max_tokens:
        logger.info("Item %s state exceeds %d tokens (%d). Truncating body.", item.id, max_tokens, tokens)
        reduction_ratio = max_tokens / max(tokens, 1)
        trimmed_len = int(len(body_text) * reduction_ratio * 0.85)
        body_text = body_text[: max(50, trimmed_len)] + "..."
        state_text = assemble(body_text, include_files=True, include_diff=True)
        tokens = estimate_tokens(state_text)

    # Step 2: Omit files and diff if still over budget
    if tokens > max_tokens:
        logger.info("Item %s still over token budget. Truncating PR files/diff.", item.id)
        state_text = assemble(body_text, include_files=False, include_diff=False)
        tokens = estimate_tokens(state_text)

    # Step 3: Hard truncate body as last resort (preserving facts intact)
    if tokens > max_tokens:
        excess = tokens - max_tokens
        char_cut = excess * 4 + 20
        body_text = body_text[: max(20, len(body_text) - char_cut)] + "..."
        state_text = assemble(body_text, include_files=False, include_diff=False)
        tokens = estimate_tokens(state_text)

    # Stable SHA256 hash (CRLF normalized to LF for cross-platform stability)
    normalized_for_hash = state_text.replace("\r\n", "\n")
    state_hash = hashlib.sha256(f"{schema_version}\n{normalized_for_hash}".encode()).hexdigest()

    return State(
        text=state_text,
        hash=state_hash,
        approx_tokens=tokens,
        facts=facts,
    )
