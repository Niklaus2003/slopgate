"""HTTP client for remote strands-decider serve instances.

Satisfies DeciderClient protocol, connecting to local or remote /v1/systemone endpoints.
Follows: architecture.md §6.3.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from typing import Any

import httpx

from slopgate.decider.client import DeciderUnavailable
from slopgate.decider.questions import hash_question_text
from slopgate.models import DeciderResult, Question, State
from slopgate.store.db import get_cached_decision, save_decision

logger = logging.getLogger(__name__)


class HttpDecider:
    """HTTP client targeting a `strands-decider serve` instance.

    Satisfies the DeciderClient protocol.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        model_id: str = "strands-decider-latest",
        timeout_seconds: float = 60.0,
        conn: sqlite3.Connection | None = None,
        item_id: int = 0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_id = model_id
        self.timeout_seconds = timeout_seconds
        self.conn = conn
        self.item_id = item_id

    def ask(self, state: State, questions: list[Question]) -> list[DeciderResult]:
        """Ask questions against a remote strands-decider server over HTTP."""
        if not questions:
            return []

        results_by_id: dict[str, DeciderResult] = {}
        missing_questions: list[Question] = []
        question_hashes: dict[str, str] = {}

        # 1. Check cache first
        for q in questions:
            q_hash = hash_question_text(q.text)
            question_hashes[q.id] = q_hash

            if self.conn:
                cached = get_cached_decision(
                    conn=self.conn,
                    question_id=q.id,
                    question_text_hash=q_hash,
                    model_id=self.model_id,
                    state_hash=state.state_hash,
                )
                if cached is not None:
                    results_by_id[q.id] = cached
                    continue

            missing_questions.append(q)

        if not missing_questions:
            return [results_by_id[q.id] for q in questions]

        # 2. Build payload
        questions_payload: dict[str, Any] = {}
        for q in missing_questions:
            if q.qtype == "choice":
                criteria = dict(q.descriptions) if q.descriptions else {opt: opt for opt in q.options}
                questions_payload[q.id] = {
                    "type": "choice",
                    "instructions": q.text,
                    "criteria": criteria,
                }
            elif q.qtype == "noul":
                questions_payload[q.id] = {
                    "type": "noul",
                    "instructions": q.text,
                }
            else:
                raise ValueError(f"Unsupported question type: {q.qtype}")

        payload = {
            "state": state.text,
            "questions": questions_payload,
            "model": self.model_id,
        }

        # 3. Send HTTP request
        url = f"{self.base_url}/v1/systemone"
        start_t = time.perf_counter()
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.ConnectError as err:
            raise DeciderUnavailable(f"Cannot connect to Decider service at {url}: {err}") from err
        except Exception as exc:
            raise DeciderUnavailable(f"Decider HTTP request failed: {exc}") from exc

        elapsed_ms = (time.perf_counter() - start_t) * 1000.0
        per_q_latency = round(elapsed_ms / max(1, len(missing_questions)), 2)

        answers = data.get("answers", {})
        for q in missing_questions:
            ans = answers.get(q.id)
            if not ans:
                raise DeciderUnavailable(f"Remote Decider omitted answer for {q.id}")

            ans_type = ans.get("type")
            if ans_type == "choice":
                result = DeciderResult(
                    question_id=q.id,
                    qtype="choice",
                    answer=ans["choice"],
                    probs=ans.get("probabilities", {}),
                    confidence=ans.get("confidence"),
                    latency_ms=per_q_latency,
                    model_id=self.model_id,
                    from_cache=False,
                )
            elif ans_type == "noul":
                p_true = float(ans["noul"])
                result = DeciderResult(
                    question_id=q.id,
                    qtype="noul",
                    answer=bool(p_true >= 0.5),
                    probs={"true": p_true, "false": round(1.0 - p_true, 4)},
                    confidence=None,
                    latency_ms=per_q_latency,
                    model_id=self.model_id,
                    from_cache=False,
                )
            else:
                raise ValueError(f"Unexpected answer type from HTTP response: {ans_type}")

            results_by_id[q.id] = result

            if self.conn:
                try:
                    save_decision(
                        conn=self.conn,
                        item_id=self.item_id,
                        decision=result,
                        verdict=None,
                        question_text_hash=question_hashes[q.id],
                        state_hash=state.state_hash,
                    )
                except Exception as save_err:  # noqa: BLE001 - cache write failure must never crash triage
                    logger.warning("Failed to cache decision: %s", save_err)

        return [results_by_id[q.id] for q in questions]
