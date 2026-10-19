"""Unit tests for DeciderClient protocol and FakeDecider test double."""

from slopgate.decider.client import DeciderClient, FakeDecider
from slopgate.models import Facts, Question, State


def test_fake_decider_implements_protocol():
    fake = FakeDecider()
    assert isinstance(fake, DeciderClient)
    assert fake.model_id == "fake-decider-2b"


def test_fake_decider_evaluates_choice_and_noul():
    fake = FakeDecider()
    state = State(
        text="[TITLE] Crash in session\n[BODY] AttributeError traceback in flask/sessions.py",
        hash="state_hash_1",
        approx_tokens=50,
        facts=Facts(has_repro_heading=True),
    )

    q1 = Question(
        id="Q1",
        qtype="choice",
        text="What kind of item is this?",
        options=("real_bug_report", "low_effort", "support_question"),
    )
    n1 = Question(
        id="N1",
        qtype="noul",
        text="Does it contain reproduction steps?",
    )

    results = fake.ask(state, [q1, n1])
    assert len(results) == 2

    r_q1 = results[0]
    assert r_q1.question_id == "Q1"
    assert r_q1.qtype == "choice"
    assert r_q1.answer == "real_bug_report"
    assert r_q1.confidence is not None
    assert r_q1.confidence > 0.80

    r_n1 = results[1]
    assert r_n1.question_id == "N1"
    assert r_n1.qtype == "noul"
    assert r_n1.answer is True
    assert r_n1.probs["true"] >= 0.85


def test_fake_decider_security_and_low_effort_detection():
    fake = FakeDecider()

    sec_state = State(
        text="Critical vulnerability report: remote code execution exploit CVE-2026-1234",
        hash="h_sec",
        approx_tokens=30,
        facts=Facts(),
    )
    q1 = Question(
        id="Q1",
        qtype="choice",
        text="Kind?",
        options=("real_bug_report", "security_report", "low_effort"),
    )
    results = fake.ask(sec_state, [q1])
    assert results[0].answer == "security_report"

    low_state = State(
        text="plz fix broken low effort",
        hash="h_low",
        approx_tokens=10,
        facts=Facts(),
    )
    results_low = fake.ask(low_state, [q1])
    assert results_low[0].answer == "low_effort"
