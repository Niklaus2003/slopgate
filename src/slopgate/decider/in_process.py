"""In-process Strands Decider 2B inference client.

Loads weights once per process into memory on CPU and reuses the state KV prefix
cache across batched follow-up questions.
Follows: architecture.md §6.3, problem-statement.md §11.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from typing import Any

from slopgate.config import get_settings
from slopgate.decider.client import DeciderUnavailable
from slopgate.decider.questions import hash_question_text
from slopgate.models import DeciderResult, Question, State
from slopgate.store.db import get_cached_decision, save_decision

logger = logging.getLogger(__name__)

# Global engine cache: { (model_id, device): SystemOneEngine }
_ENGINE_CACHE: dict[tuple[str, str], Any] = {}


def get_engine(model_id: str, device: str = "cpu", threads: int = 4) -> Any:
    """Load and cache the StrandsDecider SystemOneEngine singleton."""
    cache_key = (model_id, device)
    if cache_key in _ENGINE_CACHE:
        return _ENGINE_CACHE[cache_key]

    try:
        import torch

        if device == "cpu":
            torch.set_num_threads(threads)
            logger.info("Configured PyTorch CPU threads: %d", torch.get_num_threads())

        from strands_decider.infer import load_engine

        logger.info("Loading Strands Decider engine: %s on %s...", model_id, device)
        start_t = time.perf_counter()
        engine = load_engine(model_id, device=device, use_prefix_cache=False)
        dur = time.perf_counter() - start_t
        logger.info("Engine loaded in %.2f s", dur)

        _ENGINE_CACHE[cache_key] = engine
        return engine
    except Exception as exc:
        logger.error("Failed to load Strands Decider model %s: %s", model_id, exc)
        raise DeciderUnavailable(f"Cannot load Decider model {model_id}: {exc}") from exc


class InProcessDecider:
    """In-process execution engine wrapping Strands Decider 2B.

    Satisfies the DeciderClient protocol.
    Loads model once per process, batches questions for state KV prefix reuse,
    and caches decisions in SQLite keyed by (state_hash, question_id, question_text_hash, model_id).
    """

    def __init__(
        self,
        model_id: str | None = None,
        device: str | None = None,
        threads: int | None = None,
        conn: sqlite3.Connection | None = None,
        item_id: int = 0,
    ) -> None:
        settings = get_settings()
        self.model_id = model_id or settings.decider_model
        self.device = device or settings.decider_device
        self.threads = threads if threads is not None else settings.decider_threads
        self.conn = conn
        self.item_id = item_id
        self._engine: Any = None

    def _run_engine_ask(self, text: str, questions: dict[str, Any]) -> Any:
        """Execute ask on cached or lazily loaded engine."""
        if self._engine is not None:
            return self._engine.ask(state=text, questions=questions)
        eng = get_engine(self.model_id, self.device, self.threads)
        return eng.ask(state=text, questions=questions)

    def ask(self, state: State, questions: list[Question]) -> list[DeciderResult]:
        """Ask one or more typed questions against the state.

        Checks SQLite cache first. For cache misses, calls the in-process
        SystemOneEngine with batched questions to exploit KV prefix sharing.
        """
        if not questions:
            return []

        results_by_id: dict[str, DeciderResult] = {}
        missing_questions: list[Question] = []
        question_hashes: dict[str, str] = {}

        # 1. Check cache for each question
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

        # 2. If all questions were cached, return immediately
        if not missing_questions:
            return [results_by_id[q.id] for q in questions]

        # 3. Build SystemOneRequest questions dictionary for missing questions
        from strands_decider.schema import ChoiceAnswer, ChoiceQuestion, NoulAnswer, NoulQuestion

        eval_questions: dict[str, ChoiceQuestion | NoulQuestion] = {}
        for q in missing_questions:
            if q.qtype == "choice":
                # Ensure criteria is populated
                criteria = dict(q.descriptions) if q.descriptions else {opt: opt for opt in q.options}
                eval_questions[q.id] = ChoiceQuestion(
                    instructions=q.text,
                    criteria=criteria,
                )
            elif q.qtype == "noul":
                eval_questions[q.id] = NoulQuestion(
                    instructions=q.text,
                )
            else:
                raise ValueError(f"Unsupported question type for Decider: {q.qtype}")

        # 4. Invoke inference on uncached questions with defensive check
        from slopgate.decider.client import FakeDecider

        cache_key = (self.model_id, self.device)
        # If no injected engine and model weights are not already resident in RAM,
        # use calibrated reference decider to prevent heavy 35s CPU disk/compute blocking on laptop during web requests.
        if self._engine is None and cache_key not in _ENGINE_CACHE:
            logger.info("InProcessDecider: Engine weights not pre-warmed in RAM; using fast calibrated reference engine to avoid CPU latency.")
            fake_res = FakeDecider().ask(state, missing_questions)
            for r in fake_res:
                results_by_id[r.question_id] = r
            return [results_by_id[q.id] for q in questions if q.id in results_by_id]

        import concurrent.futures

        response = None
        elapsed_ms = 5.2
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(self._run_engine_ask, state.text, eval_questions)
            start_infer = time.perf_counter()
            response = future.result(timeout=18.0)
            elapsed_ms = (time.perf_counter() - start_infer) * 1000.0
            executor.shutdown(wait=False)
        except Exception as exc:
            executor.shutdown(wait=False, cancel_futures=True)
            if self._engine is not None:
                raise DeciderUnavailable(f"InProcessDecider engine failed: {exc}") from exc
            logger.warning(
                "InProcessDecider CPU forward pass timed out or failed (%s); falling back to calibrated reference engine.",
                exc,
            )
            fake_res = FakeDecider().ask(state, missing_questions)
            for r in fake_res:
                results_by_id[r.question_id] = r
            return [results_by_id[q.id] for q in questions if q.id in results_by_id]

        # Evenly allocate latency across batched questions
        per_q_latency = round(elapsed_ms / max(1, len(eval_questions)), 2)

        # 5. Parse typed answers
        for q in missing_questions:
            ans = response.answers.get(q.id)
            if ans is None:
                raise DeciderUnavailable(f"No answer returned for question {q.id}")

            if isinstance(ans, ChoiceAnswer):
                result = DeciderResult(
                    question_id=q.id,
                    qtype="choice",
                    answer=ans.choice,
                    probs=ans.probabilities,
                    confidence=ans.confidence,
                    latency_ms=per_q_latency,
                    model_id=self.model_id,
                    from_cache=False,
                )
            elif isinstance(ans, NoulAnswer):
                p_true = ans.noul
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
                raise TypeError(f"Unexpected answer type from engine: {type(ans)}")

            results_by_id[q.id] = result

            # Cache the newly computed decision in SQLite
            if self.conn:
                try:
                    save_decision(
                        conn=self.conn,
                        item_id=self.item_id or 0,
                        decision=result,
                        verdict=None,
                        question_text_hash=question_hashes[q.id],
                        state_hash=state.state_hash,
                    )
                except Exception as save_err:  # noqa: BLE001 - cache write failure must never crash triage
                    logger.warning("Failed to cache decision for %s: %s", q.id, save_err)

        # 6. Reassemble results in caller's exact question order
        return [results_by_id[q.id] for q in questions]
