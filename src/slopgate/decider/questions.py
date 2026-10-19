"""Canonical typed Decider questions for SlopGate.

Defines Q1 (choice for issue & PR) and N1-N5 (conditional noul follow-ups).
Only choice and noul are used; score is strictly prohibited per problem-statement.md §4.
Follows: problem-statement.md §7, architecture.md §6.4.
"""

from __future__ import annotations

import hashlib

from slopgate.models import Question

# ---------------------------------------------------------------------------
# Question Text Hashing (invalidates SQLite cache on wording changes)
# ---------------------------------------------------------------------------


def hash_question_text(text: str) -> str:
    """Compute stable SHA256 prefix hash of question text for caching."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Q1: Item Kind (Choice question asked for every item)
# ---------------------------------------------------------------------------

Q1_DEFAULT_TEXT = "Based on the item and the facts, which description best fits this contribution?"

Q1_ISSUE_OPTIONS: tuple[str, ...] = (
    "real_bug_report",
    "feature_request",
    "support_question",
    "likely_duplicate",
    "security_report",
    "low_effort",
)

Q1_ISSUE_DESCRIPTIONS: dict[str, str] = {
    "real_bug_report": "reports a specific problem with enough detail to investigate",
    "feature_request": "asks for new behavior",
    "support_question": "asks how to use the software",
    "likely_duplicate": "repeats an existing known problem",
    "security_report": "describes a possible vulnerability",
    "low_effort": "lacks concrete detail, reproduction, or a clear purpose",
}

Q1_PR_OPTIONS: tuple[str, ...] = (
    "ready_for_review",
    "needs_work",
    "out_of_scope",
    "low_effort",
)

Q1_PR_DESCRIPTIONS: dict[str, str] = {
    "ready_for_review": "clear purpose, scoped change, follows guidelines",
    "needs_work": "reasonable purpose but missing explanation, tests, or guideline compliance",
    "out_of_scope": "change unrelated to the project's goals or to an accepted issue",
    "low_effort": "unclear purpose, unrelated or trivial churn, or no explanation",
}


def get_q1_question(item_type: str, text: str = Q1_DEFAULT_TEXT) -> Question:
    """Construct canonical Q1 choice question for an issue or pull request."""
    if item_type == "pull_request":
        return Question(
            id="Q1",
            qtype="choice",
            text=text,
            options=Q1_PR_OPTIONS,
            descriptions=Q1_PR_DESCRIPTIONS,
            applies_to=("pull_request",),
        )
    return Question(
        id="Q1",
        qtype="choice",
        text=text,
        options=Q1_ISSUE_OPTIONS,
        descriptions=Q1_ISSUE_DESCRIPTIONS,
        applies_to=("issue",),
    )


# ---------------------------------------------------------------------------
# Conditional Follow-Up Questions (Noul: Yes / No)
# ---------------------------------------------------------------------------

N1_DEFAULT_TEXT = (
    "Does the text include concrete steps or code that would let a maintainer reproduce the problem?"
)
N2_DEFAULT_TEXT = (
    "Do the specific files, functions, or APIs named in the text appear in the repository facts?"
)
N3_DEFAULT_TEXT = (
    "Does the description explain why the change is needed, not only what it changes?"
)
N4_DEFAULT_TEXT = (
    "Is this the same underlying problem as the candidate duplicate listed in the facts?"
)
N5_DEFAULT_TEXT = (
    "Does the item follow the contribution guideline quoted in the facts?"
)

N1_QUESTION = Question(
    id="N1",
    qtype="noul",
    text=N1_DEFAULT_TEXT,
    applies_to=("issue",),
)

N2_QUESTION = Question(
    id="N2",
    qtype="noul",
    text=N2_DEFAULT_TEXT,
    applies_to=("issue", "pull_request"),
)

N3_QUESTION = Question(
    id="N3",
    qtype="noul",
    text=N3_DEFAULT_TEXT,
    applies_to=("pull_request",),
)

N4_QUESTION = Question(
    id="N4",
    qtype="noul",
    text=N4_DEFAULT_TEXT,
    applies_to=("issue", "pull_request"),
)

N5_QUESTION = Question(
    id="N5",
    qtype="noul",
    text=N5_DEFAULT_TEXT,
    applies_to=("issue", "pull_request"),
)

QUESTION_REGISTRY: dict[str, Question] = {
    "N1": N1_QUESTION,
    "N2": N2_QUESTION,
    "N3": N3_QUESTION,
    "N4": N4_QUESTION,
    "N5": N5_QUESTION,
}
