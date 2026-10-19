"""Unit tests for Decider cascade and early exit logic."""

from slopgate.config import load_policy
from slopgate.decider.cascade import extract_duplicate_similarity, run_cascade, select_followups
from slopgate.decider.client import FakeDecider
from slopgate.models import Band, DeciderResult, Facts, Item, State


def make_test_item(repo="pallets/flask", number=1, item_type="issue") -> Item:
    return Item(
        repo=repo,
        number=number,
        type=item_type,
        title="Test item",
        body="Test body",
        created_at="2026-10-15T12:00:00Z",
        raw={},
    )


def make_test_facts(**kwargs) -> Facts:
    default_kwargs = {
        "cited_paths_found": (1, 1),
        "has_code_block": True,
        "has_repro_heading": True,
        "template_filled": (4, 4),
        "links_to_issue": [],
        "ci_status": "unknown",
        "candidate_duplicate": None,
        "contributing_excerpt": None,
    }
    default_kwargs.update(kwargs)
    return Facts(**default_kwargs)


def test_extract_duplicate_similarity():
    assert extract_duplicate_similarity("#42 (similarity 0.71)") == 0.71
    assert extract_duplicate_similarity("issue #12 (similarity 0.85)") == 0.85
    assert extract_duplicate_similarity("none") is None
    assert extract_duplicate_similarity("") is None


def test_select_followups_early_exit_support_question():
    policy = load_policy("policy.example.yaml")
    item = make_test_item()
    facts = make_test_facts()
    q1_result = DeciderResult(
        question_id="Q1",
        qtype="choice",
        answer="support_question",
        probs={"support_question": 0.95},
        confidence=0.92,
        latency_ms=10.0,
        model_id="fake",
    )

    followups = select_followups(item, facts, q1_result, Band.HIGH, policy)
    assert followups == []


def test_select_followups_early_exit_low_effort():
    policy = load_policy("policy.example.yaml")
    item = make_test_item()
    facts = make_test_facts()
    q1_result = DeciderResult(
        question_id="Q1",
        qtype="choice",
        answer="low_effort",
        probs={"low_effort": 0.90},
        confidence=0.88,
        latency_ms=10.0,
        model_id="fake",
    )

    followups = select_followups(item, facts, q1_result, Band.HIGH, policy)
    assert followups == []


def test_select_followups_real_bug_report():
    policy = load_policy("policy.example.yaml")
    item = make_test_item()
    facts = make_test_facts()
    q1_result = DeciderResult(
        question_id="Q1",
        qtype="choice",
        answer="real_bug_report",
        probs={"real_bug_report": 0.85},
        confidence=0.82,
        latency_ms=10.0,
        model_id="fake",
    )

    followups = select_followups(item, facts, q1_result, Band.HIGH, policy)
    ids = [q.id for q in followups]
    assert ids == ["N1", "N2"]


def test_select_followups_pull_request_ready():
    policy = load_policy("policy.example.yaml")
    item = make_test_item(item_type="pull_request")
    facts = make_test_facts()
    q1_result = DeciderResult(
        question_id="Q1",
        qtype="choice",
        answer="ready_for_review",
        probs={"ready_for_review": 0.90},
        confidence=0.87,
        latency_ms=10.0,
        model_id="fake",
    )

    followups = select_followups(item, facts, q1_result, Band.HIGH, policy)
    ids = [q.id for q in followups]
    assert ids == ["N2", "N3"]


def test_select_followups_with_duplicate_and_contributing():
    policy = load_policy("policy.example.yaml")
    item = make_test_item()
    facts = make_test_facts(
        candidate_duplicate=(123, 0.75),
        contributing_excerpt="Section: Include reproducible examples",
    )
    q1_result = DeciderResult(
        question_id="Q1",
        qtype="choice",
        answer="real_bug_report",
        probs={"real_bug_report": 0.85},
        confidence=0.82,
        latency_ms=10.0,
        model_id="fake",
    )

    followups = select_followups(item, facts, q1_result, Band.HIGH, policy)
    ids = [q.id for q in followups]
    assert "N1" in ids
    assert "N2" in ids
    assert "N4" in ids
    assert "N5" in ids


def test_run_cascade_early_exit():
    policy = load_policy("policy.example.yaml")
    item = make_test_item()
    state = State(
        text="[TYPE] issue\n[TITLE] How do I install flask on Windows?\n[BODY] How do I run pip?",
        facts=make_test_facts(),
        hash="hash123",
        approx_tokens=50,
        truncated=False,
    )

    fake_decider = FakeDecider()
    results = run_cascade(item, state, fake_decider, policy)

    assert len(results) == 1
    assert results[0].question_id == "Q1"
    assert results[0].answer == "support_question"
    assert fake_decider.call_count == 1  # Only 1 call because of early exit!


def test_run_cascade_bug_report_batches_followups():
    policy = load_policy("policy.example.yaml")
    item = make_test_item()
    state = State(
        text="[TYPE] issue\n[TITLE] Crash in sessions.py\n[BODY] Steps to reproduce:\n1. run app\n2. see traceback",
        facts=make_test_facts(),
        hash="hash456",
        approx_tokens=70,
        truncated=False,
    )

    fake_decider = FakeDecider()
    results = run_cascade(item, state, fake_decider, policy)

    assert len(results) == 3
    assert [r.question_id for r in results] == ["Q1", "N1", "N2"]
    assert results[0].answer == "real_bug_report"
    # Q1 was asked (call 1), then followups were batched in one call (call 2)
    assert fake_decider.call_count == 2
