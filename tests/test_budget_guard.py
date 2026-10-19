"""Unit tests for Bedrock BudgetGuard and circuit breaker."""

from __future__ import annotations

import concurrent.futures

import pytest

from slopgate.bedrock.budget import BudgetGuard, BudgetSummary


def test_budget_guard_call_limit():
    """Verify BudgetGuard enforces call limit and trips circuit breaker."""
    guard = BudgetGuard(max_calls=3, max_cost_usd=10.0)

    # First 3 calls permitted
    assert guard.allow("call_1") is True
    guard.record_usage(tokens_in=100, tokens_out=50, cost_usd=0.001, purpose="call_1")

    assert guard.allow("call_2") is True
    guard.record_usage(tokens_in=100, tokens_out=50, cost_usd=0.001, purpose="call_2")

    assert guard.allow("call_3") is True
    guard.record_usage(tokens_in=100, tokens_out=50, cost_usd=0.001, purpose="call_3")

    # 4th call must be blocked
    assert guard.allow("call_4") is False

    summary = guard.summary()
    assert isinstance(summary, BudgetSummary)
    assert summary.calls_made == 3
    assert summary.max_calls == 3
    assert summary.is_exhausted is True
    assert summary.tokens_in == 300
    assert summary.tokens_out == 150
    assert summary.total_cost_usd == pytest.approx(0.003, 0.0001)


def test_budget_guard_cost_limit():
    """Verify BudgetGuard trips circuit breaker when cost cap is reached."""
    guard = BudgetGuard(max_calls=100, max_cost_usd=0.05)

    assert guard.allow("call_1") is True
    guard.record_usage(tokens_in=50000, tokens_out=50000, cost_usd=0.06, purpose="expensive_call")

    # Next call should be denied due to cost limit
    assert guard.allow("call_2") is False
    assert guard.summary().is_exhausted is True


def test_budget_guard_reset():
    """Verify resetting BudgetGuard restores full capacity."""
    guard = BudgetGuard(max_calls=2, max_cost_usd=1.0)
    guard.record_usage(10, 10, 0.01)
    guard.record_usage(10, 10, 0.01)
    assert guard.allow() is False

    guard.reset()
    assert guard.allow() is True
    summary = guard.summary()
    assert summary.calls_made == 0
    assert summary.tokens_in == 0
    assert summary.tokens_out == 0
    assert summary.total_cost_usd == 0.0
    assert summary.is_exhausted is False


def test_budget_guard_thread_safety():
    """Verify thread-safe updates under concurrent calls."""
    guard = BudgetGuard(max_calls=100, max_cost_usd=50.0)

    def worker(idx: int):
        if guard.allow(f"worker_{idx}"):
            guard.record_usage(tokens_in=10, tokens_out=5, cost_usd=0.0001, purpose=f"worker_{idx}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(worker, i) for i in range(50)]
        concurrent.futures.wait(futures)

    summary = guard.summary()
    assert summary.calls_made == 50
    assert summary.tokens_in == 500
    assert summary.tokens_out == 250
