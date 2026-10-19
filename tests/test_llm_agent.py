"""Unit tests for Bedrock-driven Strands LLM Agent for escalated items."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from strands.interventions import Confirm, Proceed

from slopgate.agent.llm_agent import create_escalated_agent, run_escalated_agent
from slopgate.bedrock.budget import BudgetGuard
from slopgate.config import load_policy
from slopgate.models import DeciderResult, Item
from slopgate.store.db import init_db, save_item


@pytest.fixture
def policy():
    return load_policy()


@pytest.fixture
def sample_item() -> Item:
    return Item(
        repo="pallets/flask",
        number=777,
        type="issue",
        title="Ambiguous performance issue",
        body="It is slow on my server sometimes.",
        created_at="2026-10-18T10:00:00Z",
    )


@pytest.fixture
def low_conf_results() -> list[DeciderResult]:
    return [
        DeciderResult(
            question_id="Q1",
            qtype="choice",
            answer="missing_info",
            probs={"missing_info": 0.52, "real_bug_report": 0.48},
            confidence=0.04,  # LOW band (< 0.40)
        )
    ]


@pytest.fixture
def high_conf_results() -> list[DeciderResult]:
    return [
        DeciderResult(
            question_id="Q1",
            qtype="choice",
            answer="real_bug_report",
            probs={"real_bug_report": 0.95, "other": 0.05},
            confidence=0.90,  # HIGH band (>= 0.80)
        )
    ]


def test_create_escalated_agent_wiring(sample_item, low_conf_results, policy):
    """Verify create_escalated_agent binds tools, handler, and context properly."""
    agent, ctx = create_escalated_agent(
        item=sample_item,
        results=low_conf_results,
        policy=policy,
        model="dummy-model",
        dry_run=True,
    )

    assert ctx.item.repo == "pallets/flask"
    assert ctx.item.number == 777
    assert ctx.dry_run is True
    assert len(agent.tool_registry.registry) == 5
    assert len(agent._intervention_registry.handlers) == 1
    # Check that ConfidenceBandHandler is the intervention
    handler = agent._intervention_registry.handlers[0]
    assert hasattr(handler, "before_tool_call")


def test_escalated_agent_handler_intercepts_close_item(sample_item, high_conf_results, policy):
    """CRITICAL SAFETY INVARIANT:

    Even an escalated LLM Agent cannot auto-execute close_item.
    The ConfidenceBandHandler must intercept it and return Confirm.
    """
    agent, _ctx = create_escalated_agent(
        item=sample_item,
        results=high_conf_results,
        policy=policy,
        model="dummy-model",
    )
    handler = agent._intervention_registry.handlers[0]

    # Create mock tool call event
    event = MagicMock()
    event.tool_name = "close_item"
    event.tool_use = {"name": "close_item", "input": {"reason": "Low quality"}}

    action = handler.before_tool_call(event)
    assert isinstance(action, Confirm)
    assert "INVARIANT" in action.reason


def test_escalated_agent_handler_allows_label_on_high_confidence(sample_item, high_conf_results, policy):
    """Verify tool call for apply_label proceeds under high confidence."""
    agent, _ctx = create_escalated_agent(
        item=sample_item,
        results=high_conf_results,
        policy=policy,
        model="dummy-model",
    )
    handler = agent._intervention_registry.handlers[0]

    event = MagicMock()
    event.tool_name = "apply_label"
    event.tool_use = {"name": "apply_label", "input": {"label": "bug"}}

    action = handler.before_tool_call(event)
    assert isinstance(action, Proceed)


def test_run_escalated_agent_budget_exhaustion(sample_item, low_conf_results, policy, tmp_path):
    """Verify agent immediately halts and flags for maintainer if budget cap is hit."""
    db_file = tmp_path / "test.db"
    conn = init_db(db_file)
    item_id = save_item(conn, sample_item)

    budget = BudgetGuard(max_calls=0)  # exhausted
    summary = run_escalated_agent(
        item=sample_item,
        results=low_conf_results,
        policy=policy,
        budget=budget,
        conn=conn,
        item_id=item_id,
        dry_run=True,
    )

    assert summary.status == "budget_exhausted"
    assert "cap reached" in summary.output_text.lower()
    assert "Budget cap reached on escalated item" in summary.receipt_notes
    conn.close()


def test_run_escalated_agent_successful_run(sample_item, low_conf_results, policy):
    """Verify escalated agent runs and populates AgentRunSummary."""
    budget = BudgetGuard(max_calls=5)

    with patch("slopgate.agent.llm_agent.Agent") as mock_agent_cls:
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.message = "I have reviewed this issue and requested reproduction steps."
        mock_instance.run.return_value = mock_response
        mock_agent_cls.return_value = mock_instance

        summary = run_escalated_agent(
            item=sample_item,
            results=low_conf_results,
            policy=policy,
            budget=budget,
            dry_run=True,
        )

        assert summary.status == "completed"
        assert "requested reproduction steps" in summary.output_text
        assert mock_instance.run.call_count == 1


def test_run_escalated_agent_error_handling(sample_item, low_conf_results, policy):
    """Verify execution exceptions are caught and degraded to flag_for_maintainer."""
    budget = BudgetGuard(max_calls=5)

    with patch("slopgate.agent.llm_agent.Agent") as mock_agent_cls:
        mock_instance = MagicMock()
        mock_instance.run.side_effect = RuntimeError("Strands connection timeout")
        mock_agent_cls.return_value = mock_instance

        summary = run_escalated_agent(
            item=sample_item,
            results=low_conf_results,
            policy=policy,
            budget=budget,
            dry_run=True,
        )

        assert summary.status == "error"
        assert "Strands connection timeout" in summary.output_text
        assert any("Strands connection timeout" in note for note in summary.receipt_notes)
