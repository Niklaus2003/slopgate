"""Run summary and metrics reporting for SlopGate worker runs."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


def calculate_percentiles(values: list[float]) -> tuple[float, float]:
    """Calculate p50 and p95 from a list of numeric measurements."""
    if not values:
        return 0.0, 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)

    def _percentile(p: float) -> float:
        k = (n - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_vals[int(k)]
        d0 = sorted_vals[int(f)] * (c - k)
        d1 = sorted_vals[int(c)] * (k - f)
        return d0 + d1

    p50 = _percentile(0.50)
    p95 = _percentile(0.95)
    return round(p50, 2), round(p95, 2)


@dataclass
class RunSummary:
    """Summary of an end-to-end queue processing run."""

    total_items: int = 0
    executed: int = 0
    pending_approval: int = 0
    flagged: int = 0
    dismissed: int = 0
    errors: int = 0
    total_decisions: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_hit_rate_pct: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    bedrock_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    total_cost_usd: float = 0.0
    duration_seconds: float = 0.0
    actions_executed: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert summary to JSON-serializable dictionary."""
        return {
            "total_items": self.total_items,
            "status_breakdown": {
                "executed": self.executed,
                "pending_approval": self.pending_approval,
                "flagged": self.flagged,
                "dismissed": self.dismissed,
                "errors": self.errors,
            },
            "decider": {
                "total_decisions": self.total_decisions,
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
                "cache_hit_rate_pct": self.cache_hit_rate_pct,
                "p50_latency_ms": self.p50_latency_ms,
                "p95_latency_ms": self.p95_latency_ms,
            },
            "bedrock": {
                "calls": self.bedrock_calls,
                "tokens_in": self.tokens_in,
                "tokens_out": self.tokens_out,
                "total_cost_usd": self.total_cost_usd,
            },
            "actions_executed": self.actions_executed,
            "duration_seconds": self.duration_seconds,
        }

    def format_console_report(self) -> str:
        """Format an aesthetically clean console report."""
        lines = [
            "=" * 60,
            "  SlopGate Worker Run Summary",
            "=" * 60,
            f"Items Processed:      {self.total_items:<4} (Executed: {self.executed} | Pending: {self.pending_approval} | Flagged: {self.flagged} | Errors: {self.errors})",
            f"Decider Inferences:   {self.total_decisions:<4} (Cache Hits: {self.cache_hits} [{self.cache_hit_rate_pct:.1f}%])",
            f"Decider Latency:      p50: {self.p50_latency_ms:.2f} ms | p95: {self.p95_latency_ms:.2f} ms",
            f"Bedrock Escalations:  {self.bedrock_calls:<4} calls (${self.total_cost_usd:.5f} total cost; {self.tokens_in} in / {self.tokens_out} out tokens)",
            "Actions Recorded:     " + (", ".join(f"{k}: {v}" for k, v in self.actions_executed.items()) if self.actions_executed else "None"),
            f"Wall Time Elapsed:    {self.duration_seconds:.2f}s",
            "=" * 60,
        ]
        return "\n".join(lines)
