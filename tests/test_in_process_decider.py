"""Unit tests for InProcessDecider and HttpDecider caching and mapping."""

from unittest.mock import MagicMock

import pytest
from strands_decider.schema import ChoiceAnswer, NoulAnswer, SystemOneResponse, Usage

from slopgate.decider.client import DeciderUnavailable
from slopgate.decider.http_client import HttpDecider
from slopgate.decider.in_process import InProcessDecider
from slopgate.decider.questions import N1_QUESTION, get_q1_question
from slopgate.models import Facts, State
from slopgate.store.db import init_db


def make_dummy_state(hash_str="state_hash_1", text="Test issue state") -> State:
    return State(
        text=text,
        facts=Facts(
            cited_paths_found=(0, 0),
            has_code_block=False,
            has_repro_heading=False,
            template_filled=(0, 0),
            links_to_issue=[],
            ci_status="unknown",
            candidate_duplicate=None,
            contributing_excerpt=None,
        ),
        hash=hash_str,
        approx_tokens=20,
    )


def test_in_process_decider_mocked_ask_and_caching():
    conn = init_db(":memory:")

    # Setup mock engine
    mock_engine = MagicMock()
    mock_response = SystemOneResponse(
        model="StrandsAgents/strands-decider-2B-hobson-v21",
        answers={
            "Q1": ChoiceAnswer(
                choice="real_bug_report",
                probabilities={"real_bug_report": 0.88, "support_question": 0.12},
                confidence=0.85,
            ),
            "N1": NoulAnswer(
                noul=0.92,
            ),
        },
        usage=Usage(input_tokens=100, output_tokens=2),
    )
    mock_engine.ask.return_value = mock_response

    decider = InProcessDecider(
        model_id="StrandsAgents/strands-decider-2B-hobson-v21",
        conn=conn,
    )
    decider._engine = mock_engine

    q1 = get_q1_question("issue")
    questions = [q1, N1_QUESTION]
    state = make_dummy_state("state_hash_1")

    # 1. First run: cache miss, engine called
    results = decider.ask(state, questions)
    assert len(results) == 2
    assert results[0].question_id == "Q1"
    assert results[0].answer == "real_bug_report"
    assert results[0].confidence == 0.85
    assert not results[0].from_cache

    assert results[1].question_id == "N1"
    assert results[1].answer is True
    assert results[1].probs["true"] == 0.92
    assert not results[1].from_cache

    assert mock_engine.ask.call_count == 1

    # 2. Second run with same state: 100% cache hit, engine NOT called again!
    results_cached = decider.ask(state, questions)
    assert len(results_cached) == 2
    assert results_cached[0].from_cache
    assert results_cached[0].answer == "real_bug_report"
    assert results_cached[1].from_cache
    assert results_cached[1].answer is True
    assert mock_engine.ask.call_count == 1  # Still 1!

    # 3. Third run with different state hash: cache miss, engine called
    state2 = make_dummy_state("state_hash_2", text="Different state")
    results_state2 = decider.ask(state2, questions)
    assert len(results_state2) == 2
    assert not results_state2[0].from_cache
    assert mock_engine.ask.call_count == 2


def test_in_process_decider_engine_failure_raises():
    mock_engine = MagicMock()
    mock_engine.ask.side_effect = RuntimeError("GPU/CPU memory fault")

    decider = InProcessDecider(model_id="test-model")
    decider._engine = mock_engine

    state = make_dummy_state()
    q1 = get_q1_question("issue")

    with pytest.raises(DeciderUnavailable):
        decider.ask(state, [q1])


def test_http_decider_connection_failure():
    decider = HttpDecider(base_url="http://127.0.0.1:54321")
    state = make_dummy_state()
    q1 = get_q1_question("issue")

    with pytest.raises(DeciderUnavailable):
        decider.ask(state, [q1])
