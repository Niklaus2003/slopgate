"""Unit tests for Decider typed questions."""

from slopgate.decider.questions import (
    N1_QUESTION,
    N2_QUESTION,
    N3_QUESTION,
    N4_QUESTION,
    N5_QUESTION,
    QUESTION_REGISTRY,
    get_q1_question,
    hash_question_text,
)


def test_q1_issue_definition():
    q = get_q1_question("issue")
    assert q.id == "Q1"
    assert q.qtype == "choice"
    assert "real_bug_report" in q.options
    assert "support_question" in q.options
    assert "low_effort" in q.options
    assert len(q.options) == 6
    assert len(q.descriptions) == 6
    assert q.applies_to == ("issue",)


def test_q1_pull_request_definition():
    q = get_q1_question("pull_request")
    assert q.id == "Q1"
    assert q.qtype == "choice"
    assert "ready_for_review" in q.options
    assert "needs_work" in q.options
    assert "low_effort" in q.options
    assert len(q.options) == 4
    assert len(q.descriptions) == 4
    assert q.applies_to == ("pull_request",)


def test_noul_questions_definition():
    assert N1_QUESTION.qtype == "noul"
    assert N1_QUESTION.applies_to == ("issue",)

    assert N2_QUESTION.qtype == "noul"
    assert "issue" in N2_QUESTION.applies_to
    assert "pull_request" in N2_QUESTION.applies_to

    assert N3_QUESTION.qtype == "noul"
    assert N3_QUESTION.applies_to == ("pull_request",)

    assert N4_QUESTION.qtype == "noul"
    assert N5_QUESTION.qtype == "noul"

    assert len(QUESTION_REGISTRY) == 5


def test_hash_question_text_stability():
    t1 = "Does the text include concrete steps?"
    t2 = "  Does the text include concrete steps?  "
    t3 = "A different question altogether"

    h1 = hash_question_text(t1)
    h2 = hash_question_text(t2)
    h3 = hash_question_text(t3)

    assert h1 == h2
    assert len(h1) == 16
    assert h1 != h3
