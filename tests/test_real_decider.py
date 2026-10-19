"""Integration test for InProcessDecider using the real model weights on CPU.

Marked @pytest.mark.slow. Tests real inference, cascade evaluation, and SQLite caching.
Follows: implementation-plan.md Phase 4 Step 7.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slopgate.config import load_policy
from slopgate.decider.cascade import run_cascade
from slopgate.decider.in_process import InProcessDecider
from slopgate.ingest.replay import load_replay_items
from slopgate.state.builder import build_state
from slopgate.state.repo_index import RepoIndex
from slopgate.store.db import init_db

ROOT_DIR = Path(__file__).resolve().parent.parent
SAMPLES_DIR = ROOT_DIR / "data" / "samples"


@pytest.mark.slow
def test_real_decider_inference_cascade_and_cache():
    items_path = SAMPLES_DIR / "flask.json"
    tree_path = SAMPLES_DIR / "flask_tree.json"

    if not items_path.is_file() or not tree_path.is_file():
        pytest.skip("Sample replay data not available")

    policy = load_policy(ROOT_DIR / "policy.example.yaml")
    items = load_replay_items(items_path)[:3]
    tree_files = json.loads(tree_path.read_text(encoding="utf-8"))
    repo_index = RepoIndex.from_file_list(tree_files)

    states = [build_state(item, policy=policy, repo_index=repo_index) for item in items]

    # Initialize SQLite in-memory DB for caching
    conn = init_db(":memory:")
    decider = InProcessDecider(conn=conn)

    # First pass: Real model inference
    first_pass_results = []
    for item, state in zip(items, states, strict=False):
        results = run_cascade(item, state, decider, policy)
        assert len(results) >= 1
        q1_res = results[0]
        assert q1_res.question_id == "Q1"
        assert q1_res.qtype == "choice"
        assert q1_res.answer in q1_res.probs
        assert not q1_res.from_cache
        first_pass_results.append(results)

    # Second pass: 100% cache hit test (zero model calls)
    for idx, (item, state) in enumerate(zip(items, states, strict=False)):
        cached_results = run_cascade(item, state, decider, policy)
        assert len(cached_results) == len(first_pass_results[idx])
        for r in cached_results:
            assert r.from_cache, f"Expected decision for {r.question_id} to be from cache"
