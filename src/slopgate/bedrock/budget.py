"""Bedrock Budget Guard and Circuit Breaker.

Strictly bounds AWS Bedrock usage per run:
- Enforces call limit (default: 50 calls per run)
- Enforces optional cost limit (default: $5.00)
- Tracks input/output token consumption and total USD expenditure
- Triggers graceful degradation when cap is reached

Follows: architecture.md §6.7, §11, docs/defense/02_CONSTRAINTS.md (INVARIANT 4).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

from slopgate.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class BudgetSummary:
    """Summary of token and cost expenditure for a run."""

    calls_made: int
    max_calls: int
    tokens_in: int
    tokens_out: int
    total_cost_usd: float
    is_exhausted: bool


class BudgetGuard:
    """Thread-safe circuit breaker monitoring Bedrock calls and cost."""

    def __init__(
        self,
        max_calls: int | None = None,
        max_cost_usd: float = 5.0,
    ) -> None:
        settings = get_settings()
        self.max_calls = max_calls if max_calls is not None else settings.max_bedrock_calls
        self.max_cost_usd = max_cost_usd

        self._lock = threading.Lock()
        self._calls_made = 0
        self._tokens_in = 0
        self._tokens_out = 0
        self._total_cost_usd = 0.0
        self._call_log: list[dict[str, Any]] = []

    def allow(self, purpose: str = "") -> bool:
        """Check if an additional Bedrock call is permitted under budget."""
        with self._lock:
            if self._calls_made >= self.max_calls:
                logger.warning(
                    "Bedrock budget cap reached: %d/%d calls exhausted for purpose '%s'. Circuit breaker open.",
                    self._calls_made,
                    self.max_calls,
                    purpose,
                )
                return False

            if self._total_cost_usd >= self.max_cost_usd:
                logger.warning(
                    "Bedrock cost cap reached: $%.4f/$%.2f exhausted for purpose '%s'. Circuit breaker open.",
                    self._total_cost_usd,
                    self.max_cost_usd,
                    purpose,
                )
                return False

            return True

    def record_usage(
        self,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
        purpose: str = "",
    ) -> None:
        """Record token counts and cost for an executed Bedrock call."""
        with self._lock:
            self._calls_made += 1
            self._tokens_in += tokens_in
            self._tokens_out += tokens_out
            self._total_cost_usd += cost_usd

            self._call_log.append(
                {
                    "call_number": self._calls_made,
                    "purpose": purpose,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "cost_usd": cost_usd,
                }
            )

            logger.info(
                "Bedrock call #%d [%s]: %d in / %d out tokens ($%.5f). Total cost: $%.5f",
                self._calls_made,
                purpose,
                tokens_in,
                tokens_out,
                cost_usd,
                self._total_cost_usd,
            )

    def summary(self) -> BudgetSummary:
        """Return the current budget consumption status."""
        with self._lock:
            is_exhausted = (self._calls_made >= self.max_calls) or (self._total_cost_usd >= self.max_cost_usd)
            return BudgetSummary(
                calls_made=self._calls_made,
                max_calls=self.max_calls,
                tokens_in=self._tokens_in,
                tokens_out=self._tokens_out,
                total_cost_usd=round(self._total_cost_usd, 5),
                is_exhausted=is_exhausted,
            )

    def reset(self) -> None:
        """Reset budget counters for a new worker run."""
        with self._lock:
            self._calls_made = 0
            self._tokens_in = 0
            self._tokens_out = 0
            self._total_cost_usd = 0.0
            self._call_log.clear()
