"""Smoke test for Strands Decider 2B on CPU: load once, ask multiple questions, measure latency."""

import os
import sys
import time

# Ensure slopgate is on import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from slopgate.config import get_settings

SAMPLE_REALISTIC_STATE = """[TYPE] issue
[TITLE] TypeError: Cannot read property 'get' of undefined in session handler
[BODY] When running the test suite with Python 3.12, the session middleware fails during teardown.
Traceback:
  File "flask/sessions.py", line 142, in open_session
    val = request.cookies.get(self.key)
AttributeError: 'NoneType' object has no attribute 'get'
Steps to reproduce:
1. Configure session cookie domain to localhost
2. Send request without cookie header
3. Observe crash during response handling
[FACTS]
- cited_paths_found: 1 of 1 (flask/sessions.py)
- has_code_block: yes
- has_repro_heading: yes
- template_sections_filled: 4 of 4
- links_to_issue: none
- ci_status: unknown
- candidate_duplicate: none
"""


def main():
    settings = get_settings()
    print("=" * 60)
    print("  Strands Decider 2B CPU Smoke Test")
    print("=" * 60)
    print(f"Model ID: {settings.decider_model}")
    print(f"Device:   {settings.decider_device}")
    print(f"Threads:  {settings.decider_threads}")

    try:
        import torch
        torch.set_num_threads(settings.decider_threads)
        print(f"PyTorch threads configured: {torch.get_num_threads()}")
    except ImportError:
        print("PyTorch not installed yet.")
        return 1

    try:
        from strands_decider.modeling import StrandsDeciderModel
    except ImportError as e:
        print(f"strands-decider not installed yet: {e}")
        return 1

    print("\nLoading model weights (in-process, CPU)...")
    start_load = time.perf_counter()
    model = StrandsDeciderModel.load(settings.decider_model)
    load_duration = time.perf_counter() - start_load
    print(f"Model loaded successfully in {load_duration:.2f} s")

    # Warm-up call
    print("\nExecuting warm-up question...")
    start_warm = time.perf_counter()
    _ = model.ask(
        state="Test state",
        questions=[{"text": "Is this a test?", "type": "noul"}]
    )
    warm_duration = time.perf_counter() - start_warm
    print(f"Warm-up complete in {warm_duration:.2f} s")

    # Benchmark: 5 questions on the same ~400-token state
    questions = [
        {
            "id": "Q1",
            "type": "choice",
            "text": "Based on the item and the facts, which description best fits this contribution?",
            "options": [
                "real_bug_report",
                "feature_request",
                "support_question",
                "likely_duplicate",
                "low_effort",
            ],
        },
        {
            "id": "N1",
            "type": "noul",
            "text": "Does the text include concrete steps or code that would let a maintainer reproduce the problem?",
        },
        {
            "id": "N2",
            "type": "noul",
            "text": "Do the specific files, functions, or APIs named in the text appear in the repository facts?",
        },
    ]

    print("\nRunning multi-question benchmark on realistic state (batched)...")
    start_bench = time.perf_counter()
    results = model.ask(state=SAMPLE_REALISTIC_STATE, questions=questions)
    total_bench = time.perf_counter() - start_bench

    print(f"All {len(questions)} questions answered in {total_bench:.3f} s total ({total_bench/len(questions):.3f} s/question)")
    for q, r in zip(questions, results):
        print(f"  - [{q['id']}] {r}")

    print("\nSmoke test PASSED!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
