"""Unit tests for calculate_percentiles and RunSummary reporting."""

from __future__ import annotations

from slopgate.report.summary import RunSummary, calculate_percentiles


def test_calculate_percentiles_empty_and_single():
    """Verify percentile calculation on edge case lists."""
    assert calculate_percentiles([]) == (0.0, 0.0)
    assert calculate_percentiles([42.5]) == (42.5, 42.5)


def test_calculate_percentiles_distribution():
    """Verify p50 and p95 on known distribution."""
    # 1 to 100
    values = [float(i) for i in range(1, 101)]
    p50, p95 = calculate_percentiles(values)

    assert 49.0 <= p50 <= 52.0
    assert 94.0 <= p95 <= 96.0


def test_run_summary_formatting_and_dict():
    """Verify RunSummary dictionary export and console rendering."""
    summary = RunSummary(
        total_items=25,
        executed=20,
        pending_approval=4,
        flagged=1,
        dismissed=0,
        errors=0,
        total_decisions=48,
        cache_hits=40,
        cache_misses=8,
        cache_hit_rate_pct=83.33,
        p50_latency_ms=12.4,
        p95_latency_ms=45.8,
        bedrock_calls=3,
        tokens_in=350,
        tokens_out=85,
        total_cost_usd=0.00045,
        duration_seconds=3.21,
        actions_executed={"apply_label": 20, "request_info_comment": 4},
    )

    data = summary.to_dict()
    assert data["total_items"] == 25
    assert data["status_breakdown"]["executed"] == 20
    assert data["decider"]["cache_hit_rate_pct"] == 83.33
    assert data["bedrock"]["calls"] == 3
    assert data["actions_executed"]["apply_label"] == 20

    text = summary.format_console_report()
    assert "SlopGate Worker Run Summary" in text
    assert "Items Processed:      25" in text
    assert "Cache Hits: 40 [83.3%]" in text
    assert "p50: 12.40 ms | p95: 45.80 ms" in text
    assert "$0.00045 total cost" in text
