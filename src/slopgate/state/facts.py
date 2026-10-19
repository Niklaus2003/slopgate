"""Deterministic, cheap code-based fact extractors.

Extracts verifiable evidence from item text and repo index with zero AI calls.
Follows: problem-statement.md §6.2, architecture.md §6.2.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from slopgate.models import Facts, Item
from slopgate.state.repo_index import RepoIndex
from slopgate.state.similarity import find_candidate_duplicate

# Regex patterns for deterministic extraction
_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```|~~~[\s\S]*?~~~", re.MULTILINE)
_REPRO_HEADING_RE = re.compile(
    r"#{1,6}\s*(?:steps\s+to\s+reproduce|reproduction(?:\s+steps)?|how\s+to\s+reproduce|to\s+reproduce|minimal\s+repro|repro)",
    re.IGNORECASE,
)
_ISSUE_LINK_RE = re.compile(
    r"(?:(?:fixes|closes|resolves|see|ref)\s+#(\d+)|#(\d+)|/issues/(\d+))",
    re.IGNORECASE,
)

DEFAULT_TEMPLATE_HEADINGS = [
    "Environment",
    "Description",
    "Steps to Reproduce",
    "Expected Behavior",
]


def check_has_code_block(text: str) -> bool:
    """Check if markdown contains fenced code blocks or indentation."""
    if not text:
        return False
    if _CODE_BLOCK_RE.search(text):
        return True
    # Also check indented lines (>4 spaces followed by code-like syntax)
    for line in text.splitlines():
        if line.startswith("    ") and any(c in line for c in ("=", "(", ")", "def ", "import ")):
            return True
    return False


def check_has_repro_heading(text: str) -> bool:
    """Check if markdown contains an explicit reproduction section header."""
    if not text:
        return False
    return bool(_REPRO_HEADING_RE.search(text))


def check_template_sections_filled(
    text: str,
    template_headings: list[str] | None = None,
) -> tuple[int, int]:
    """Check how many standard template section headings are present and non-empty.

    Returns:
        (filled_sections, total_sections)
    """
    headings = template_headings or DEFAULT_TEMPLATE_HEADINGS
    if not text:
        return 0, len(headings)

    text_lower = text.lower()
    filled = 0

    for h in headings:
        h_lower = h.lower()
        if h_lower in text_lower:
            # Check that content follows the heading
            pos = text_lower.find(h_lower)
            snippet_after = text[pos + len(h_lower) : pos + len(h_lower) + 100].strip()
            # If not immediately hitting another heading or empty string
            if snippet_after and not snippet_after.startswith("#"):
                filled += 1

    return filled, len(headings)


def extract_links_to_issue(text: str) -> list[int]:
    """Extract referenced issue/PR numbers from text."""
    if not text:
        return []

    found_numbers: set[int] = set()
    for m in _ISSUE_LINK_RE.finditer(text):
        for group in m.groups():
            if group and group.isdigit():
                found_numbers.add(int(group))

    return sorted(found_numbers)


def extract_contributing_summary(
    text: str,
    contributing_rules: dict[str, str] | None = None,
) -> str | None:
    """Keyword match against common CONTRIBUTING guidelines."""
    rules = contributing_rules or {
        "test": "CONTRIBUTING: All bug fixes must include regression unit tests.",
        "docs": "CONTRIBUTING: Documentation updates must accompany user-facing changes.",
        "changelog": "CONTRIBUTING: Please add a note to CHANGES.rst.",
    }

    text_lower = text.lower()
    for kw, rule_summary in rules.items():
        if kw in text_lower:
            return rule_summary
    return None


def extract_ci_status(item: Item) -> str:
    """Extract CI status from pull request raw payload or item fields."""
    if item.ci_status and item.ci_status != "unknown":
        return item.ci_status

    if isinstance(item.raw, dict):
        # Inspect GitHub checks or status summary if present
        head_commit = item.raw.get("head", {})
        if isinstance(head_commit, dict) and "status" in head_commit:
            return str(head_commit["status"]).lower()

    return "unknown"


def extract_all_facts(
    item: Item,
    repo_index: RepoIndex | None = None,
    candidates: Sequence[Item] | None = None,
    similarity_min: float = 0.55,
    include_author_history: bool = False,
    template_headings: list[str] | None = None,
) -> Facts:
    """Extract all deterministic facts for an item."""
    text_content = f"{item.title}\n\n{item.body}"

    # 1. Cited paths
    if repo_index:
        cited_paths = repo_index.extract_cited_paths(text_content)
    else:
        cited_paths = (0, 0)

    # 2. Code block
    has_code = check_has_code_block(item.body)

    # 3. Repro heading
    has_repro = check_has_repro_heading(item.body)

    # 4. Template sections
    template_filled = check_template_sections_filled(
        item.body, template_headings=template_headings
    )

    # 5. Linked issues
    linked_issues = extract_links_to_issue(text_content)

    # 6. CI status
    ci_status = extract_ci_status(item)

    # 7. Candidate duplicate
    candidate_dup = None
    if candidates:
        candidate_dup = find_candidate_duplicate(
            target_item=item,
            candidates=candidates,
            similarity_min=similarity_min,
        )

    # 8. Contributing excerpt
    contributing_summary = extract_contributing_summary(text_content)

    # 9. Author history (excluded by default)
    author_hist = None
    if include_author_history and item.author_login:
        author_hist = f"author: {item.author_login}"

    return Facts(
        cited_paths_found=cited_paths,
        has_code_block=has_code,
        has_repro_heading=has_repro,
        template_filled=template_filled,
        links_to_issue=linked_issues,
        ci_status=ci_status,
        candidate_duplicate=candidate_dup,
        contributing_excerpt=contributing_summary,
        author_history=author_hist,
    )
