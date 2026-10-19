"""Live integration tests for Amazon Bedrock API.

Marked @pytest.mark.live. Requires valid AWS credentials with Bedrock Converse access.
Follows: implementation-plan.md Phase 6 Step 6 and Exit Criterion 1.
"""

from __future__ import annotations

import os

import pytest

from slopgate.bedrock.client import BedrockClient, BedrockError
from slopgate.bedrock.escalate import draft_reply, reason_on_ambiguous
from slopgate.config import get_settings
from slopgate.models import Facts, Item


@pytest.mark.live
def test_live_bedrock_converse_call():
    """Verify BedrockClient against real AWS Bedrock Converse API endpoint."""
    settings = get_settings()

    if not (settings.aws_access_key_id and settings.aws_secret_access_key) and not os.environ.get("AWS_PROFILE"):
        pytest.skip("AWS credentials not configured in environment or .env")

    client = BedrockClient()
    try:
        resp = client.invoke(
            prompt="Hello Bedrock, please confirm you are online.",
            system_prompt="Respond in exactly 5 words.",
            max_tokens=20,
        )
        assert resp.text != ""
        assert resp.tokens_in > 0
        assert resp.tokens_out > 0
        assert resp.est_cost_usd >= 0.0
    except BedrockError as err:
        err_msg = str(err).lower()
        if "operation not allowed" in err_msg or "accessdenied" in err_msg or "validationexception" in err_msg:
            pytest.skip(f"AWS Bedrock account verification pending or model access not yet granted: {err}")
        raise


@pytest.mark.live
def test_live_bedrock_draft_and_reason():
    """Verify draft_reply and reason_on_ambiguous against real Bedrock endpoint."""
    settings = get_settings()

    if not (settings.aws_access_key_id and settings.aws_secret_access_key) and not os.environ.get("AWS_PROFILE"):
        pytest.skip("AWS credentials not configured in environment or .env")

    client = BedrockClient()
    item = Item(
        repo="pallets/flask",
        number=999,
        type="issue",
        title="Live Bedrock verification",
        body="Testing connection to Bedrock Nova or Claude models.",
        created_at="2026-10-18T10:00:00Z",
    )
    facts = Facts(
        cited_paths_found=(0, 0),
        has_code_block=False,
        has_repro_heading=False,
        template_filled=(0, 0),
        candidate_duplicate=None,
        ci_status="neutral",
    )

    try:
        draft = draft_reply(item=item, client=client)
        assert isinstance(draft, str)
        assert len(draft) > 0

        reasoning = reason_on_ambiguous(
            item=item,
            facts=facts,
            decider_probs={"real_bug": 0.5, "missing_info": 0.5},
            client=client,
        )
        assert isinstance(reasoning, dict)
        assert "suggested_label" in reasoning
        assert reasoning["needs_maintainer_review"] is True
    except BedrockError as err:
        err_msg = str(err).lower()
        if "operation not allowed" in err_msg or "accessdenied" in err_msg or "validationexception" in err_msg:
            pytest.skip(f"AWS Bedrock account verification pending: {err}")
        raise
