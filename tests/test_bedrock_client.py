"""Unit tests for BedrockClient, pricing estimation, and MockBedrockClient."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from slopgate.bedrock.client import (
    BedrockClient,
    BedrockError,
    BedrockResponse,
    BedrockThrottledError,
    MockBedrockClient,
    estimate_bedrock_cost,
)


def test_estimate_bedrock_cost_models():
    """Verify cost calculation across different Bedrock model rates."""
    # Nova Micro: $0.035 in / $0.140 out per 1M
    cost_micro = estimate_bedrock_cost("amazon.nova-micro-v1:0", 1_000_000, 1_000_000)
    assert pytest.approx(cost_micro, 0.001) == 0.175

    # Nova Pro: $0.800 in / $3.200 out per 1M
    cost_pro = estimate_bedrock_cost("amazon.nova-pro-v1:0", 100_000, 50_000)
    # (0.1 * 0.8) + (0.05 * 3.2) = 0.08 + 0.16 = 0.24
    assert pytest.approx(cost_pro, 0.001) == 0.24

    # Claude 3.5 Sonnet: $3.00 in / $15.00 out per 1M
    cost_sonnet = estimate_bedrock_cost("anthropic.claude-3-5-sonnet-20241022-v2:0", 10_000, 1_000)
    # (0.01 * 3) + (0.001 * 15) = 0.03 + 0.015 = 0.045
    assert pytest.approx(cost_sonnet, 0.001) == 0.045

    # Unknown model fallback: 0.05 / 0.20 per 1M
    cost_fallback = estimate_bedrock_cost("unknown.model:1", 1_000_000, 1_000_000)
    assert pytest.approx(cost_fallback, 0.001) == 0.25


def test_mock_bedrock_client_canned_text():
    """Verify MockBedrockClient returns deterministic canned text and records call history."""
    client = MockBedrockClient(canned_text="Please provide a minimal reproducible example.")
    resp = client.invoke("Analyze issue 123", system_prompt="System instructions")

    assert isinstance(resp, BedrockResponse)
    assert resp.text == "Please provide a minimal reproducible example."
    assert resp.tokens_in == 150
    assert resp.tokens_out == 45
    assert resp.est_cost_usd > 0
    assert len(client.call_history) == 1
    assert client.call_history[0]["prompt"] == "Analyze issue 123"
    assert client.call_history[0]["system_prompt"] == "System instructions"


def test_mock_bedrock_client_canned_json():
    """Verify MockBedrockClient returns serialized canned json dictionary."""
    data = {
        "suggested_label": "needs-repro",
        "rationale": "Missing minimal repro",
        "needs_maintainer_review": True,
    }
    client = MockBedrockClient(canned_json=data)
    resp = client.invoke("Classify this issue")

    import json

    parsed = json.loads(resp.text)
    assert parsed["suggested_label"] == "needs-repro"
    assert parsed["needs_maintainer_review"] is True


def test_bedrock_client_success_converse():
    """Verify BedrockClient properly parses Converse API response."""
    mock_boto = MagicMock()
    mock_boto.converse.return_value = {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": "Thank you for reporting this bug."}],
            }
        },
        "usage": {
            "inputTokens": 80,
            "outputTokens": 25,
        },
    }

    client = BedrockClient(
        region_name="us-east-1",
        model_id="amazon.nova-micro-v1:0",
        boto_client=mock_boto,
    )
    resp = client.invoke("Draft a reply", system_prompt="Be kind")

    assert resp.text == "Thank you for reporting this bug."
    assert resp.tokens_in == 80
    assert resp.tokens_out == 25
    assert resp.model_id == "amazon.nova-micro-v1:0"
    assert resp.est_cost_usd > 0
    assert mock_boto.converse.call_count == 1


def test_bedrock_client_throttling_retry(monkeypatch):
    """Verify BedrockClient retries on throttling errors and raises BedrockThrottledError when exhausted."""
    # Speed up sleep in tests
    monkeypatch.setattr("time.sleep", lambda s: None)

    mock_boto = MagicMock()
    mock_boto.converse.side_effect = Exception("ThrottlingException: Rate exceeded")

    client = BedrockClient(
        region_name="us-east-1",
        model_id="amazon.nova-micro-v1:0",
        max_retries=2,
        boto_client=mock_boto,
    )

    with pytest.raises(BedrockThrottledError) as exc_info:
        client.invoke("Draft a reply")

    assert "throttled after 2 retries" in str(exc_info.value).lower()
    # Initial call + 2 retries = 3 calls
    assert mock_boto.converse.call_count == 3


def test_bedrock_client_non_retryable_error():
    """Verify BedrockClient raises BedrockError immediately without retry on fatal errors."""
    mock_boto = MagicMock()
    mock_boto.converse.side_effect = Exception("ValidationException: Model access not granted")

    client = BedrockClient(
        region_name="us-east-1",
        model_id="amazon.nova-micro-v1:0",
        max_retries=3,
        boto_client=mock_boto,
    )

    with pytest.raises(BedrockError) as exc_info:
        client.invoke("Draft a reply")

    assert "ValidationException" in str(exc_info.value)
    # Non-retryable error should only call once
    assert mock_boto.converse.call_count == 1
