"""Unit tests for Bedrock escalation functions (draft_reply and reason_on_ambiguous)."""

from __future__ import annotations

import pytest

from slopgate.bedrock.budget import BudgetGuard
from slopgate.bedrock.client import MockBedrockClient
from slopgate.bedrock.escalate import draft_reply, reason_on_ambiguous
from slopgate.models import Facts, Item
from slopgate.store.db import get_escalations_for_item, init_db, save_item


@pytest.fixture
def sample_item() -> Item:
    return Item(
        repo="psf/requests",
        number=123,
        type="issue",
        title="SSL verification failed on custom cert",
        body="Traceback occurs when cert is loaded.",
        created_at="2026-10-18T10:00:00Z",
    )


@pytest.fixture
def sample_facts() -> Facts:
    return Facts(
        cited_paths_found=(1, 1),
        has_code_block=True,
        has_repro_heading=True,
        template_filled=(2, 2),
        candidate_duplicate=None,
        ci_status="neutral",
    )


def test_draft_reply_normal(sample_item):
    """Verify draft_reply invokes Bedrock and returns polite response."""
    canned_text = "Thanks for opening this issue! Could you share the Python and OpenSSL versions used?"
    client = MockBedrockClient(canned_text=canned_text)
    budget = BudgetGuard(max_calls=10)

    result = draft_reply(
        item=sample_item,
        receipt_notes=["Missing version information"],
        client=client,
        budget=budget,
    )

    assert result == canned_text
    assert budget.summary().calls_made == 1


def test_draft_reply_rejection_of_forbidden_accusations(sample_item):
    """Verify safety guardrail intercepts forbidden accusatory terms and degrades to template."""
    hostile_model_output = "This looks like AI-generated slop from a low effort bot."
    client = MockBedrockClient(canned_text=hostile_model_output)
    budget = BudgetGuard(max_calls=10)

    result = draft_reply(
        item=sample_item,
        client=client,
        budget=budget,
    )

    # Must NOT contain the forbidden words
    assert "slop" not in result.lower()
    assert "ai" not in result.lower()
    assert "bot" not in result.lower()
    # Must contain courteous template request
    assert "Thanks for opening this issue!" in result
    assert "Minimal reproduction steps" in result


def test_draft_reply_truncates_long_response(sample_item):
    """Verify drafts longer than 150 words are truncated safely."""
    long_text = " ".join(["word"] * 200)
    client = MockBedrockClient(canned_text=long_text)
    budget = BudgetGuard(max_calls=10)

    result = draft_reply(
        item=sample_item,
        client=client,
        budget=budget,
    )

    words = result.split()
    assert len(words) <= 125
    assert result.endswith("...")


def test_draft_reply_budget_exhaustion_degrades(sample_item):
    """Verify budget exhaustion immediately returns polite template without calling Bedrock."""
    client = MockBedrockClient(canned_text="Should not be called")
    budget = BudgetGuard(max_calls=0)  # zero calls allowed

    result = draft_reply(
        item=sample_item,
        template_hint="bug",
        client=client,
        budget=budget,
    )

    assert len(client.call_history) == 0
    assert "Thanks for opening this issue!" in result
    assert "Steps to reproduce" in result


def test_draft_reply_persists_escalation_in_sqlite(sample_item, tmp_path):
    """Verify token usage, cost, and output text are persisted in escalations table."""
    db_file = tmp_path / "test.db"
    conn = init_db(db_file)
    item_id = save_item(conn, sample_item)

    canned_text = "Please provide exact steps to reproduce."
    client = MockBedrockClient(
        canned_text=canned_text,
        tokens_in=200,
        tokens_out=40,
        model_id="amazon.nova-micro-v1:0",
    )
    budget = BudgetGuard(max_calls=10)

    draft_reply(
        item=sample_item,
        client=client,
        budget=budget,
        conn=conn,
        item_id=item_id,
    )

    escalations = get_escalations_for_item(conn, item_id)
    assert len(escalations) == 1
    esc = escalations[0]
    assert esc["purpose"] == "draft_reply"
    assert esc["bedrock_model"] == "amazon.nova-micro-v1:0"
    assert esc["tokens_in"] == 200
    assert esc["tokens_out"] == 40
    assert esc["est_cost_usd"] > 0
    assert esc["output_text"] == canned_text
    conn.close()


def test_reason_on_ambiguous_valid_json(sample_item, sample_facts):
    """Verify reason_on_ambiguous returns parsed structured classification."""
    canned_json = {
        "suggested_label": "needs-repro",
        "rationale": "Missing minimal reproducible example for SSL cert error.",
        "needs_maintainer_review": True,
    }
    client = MockBedrockClient(canned_json=canned_json)
    budget = BudgetGuard(max_calls=10)

    result = reason_on_ambiguous(
        item=sample_item,
        facts=sample_facts,
        decider_probs={"real_bug_report": 0.51, "missing_info": 0.49},
        client=client,
        budget=budget,
    )

    assert result["suggested_label"] == "needs-repro"
    assert "Missing minimal" in result["rationale"]
    assert result["needs_maintainer_review"] is True


def test_reason_on_ambiguous_invalid_json_fallback(sample_item, sample_facts):
    """Verify unparseable LLM output safely degrades to maintainer review."""
    client = MockBedrockClient(canned_text="I think this is an ambiguous bug report without JSON.")
    budget = BudgetGuard(max_calls=10)

    result = reason_on_ambiguous(
        item=sample_item,
        facts=sample_facts,
        decider_probs={"real_bug_report": 0.50, "other": 0.50},
        client=client,
        budget=budget,
    )

    assert result["suggested_label"] == "needs-triage"
    assert result["needs_maintainer_review"] is True
    assert "requires maintainer review" in result["rationale"]


def test_reason_on_ambiguous_budget_exhaustion(sample_item, sample_facts):
    """Verify reasoning degrades gracefully to maintainer flag when budget cap is met."""
    client = MockBedrockClient(canned_text="Should not run")
    budget = BudgetGuard(max_calls=0)

    result = reason_on_ambiguous(
        item=sample_item,
        facts=sample_facts,
        decider_probs={"real_bug": 0.5},
        client=client,
        budget=budget,
    )

    assert len(client.call_history) == 0
    assert result["suggested_label"] == "needs-triage"
    assert result["needs_maintainer_review"] is True
    assert "Budget cap reached" in result["rationale"]
