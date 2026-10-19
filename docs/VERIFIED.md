# SlopGate — Verified Technical Facts & API Findings

> **Purpose:** Empirical log of verified technical facts, API signatures, CPU latencies, and package behaviors. Every statement in this file was directly measured or verified via source code / experiments.

---

## 1. Hardware & Environment Baseline
- **Date:** 2026-10-15
- **CPU Model:** 13th Gen Intel(R) Core(TM) i5-1335U (10 Cores: 2 Performance-cores, 8 Efficient-cores, 12 Threads)
- **RAM:** 15.69 GB Physical RAM
- **Operating System:** Windows 11 (64-bit)
- **Python Version:** Python 3.12.10
- **Virtual Environment Path:** `c:\Users\AaronFrancis\Desktop\vscode\research\aws_hackathon\.venv\Scripts\python.exe`
- **PyTorch Threading Decision:** Set `SLOPGATE_DECIDER_THREADS=4` to isolate execution to high-performance cores and prevent thread-synchronization penalties across asymmetric E-cores.

---

## 2. Seven `VERIFY` Items Tracking (from `architecture.md` §16)

| ID | Topic | Target | Status | Verification Result & Notes |
|---|---|---|---|---|
| **V1** | Decider multi-question batch API (prefix reuse) | `strands_decider.infer` | Verified | `SystemOneEngine._slot_probs_shared_prefix` encodes state once via `torso(..., use_cache=True)`, broadcasts KV cache across questions via `_expand_cache`, forwarding only short question suffixes. |
| **V2** | `InterventionHandler` class & return types (`Proceed`, `Deny`, `Confirm`, `Guide`) | `strands.interventions` | Verified | `InterventionHandler` requires abstract property `name: str`. Lifecycle hook `before_tool_call(event: BeforeToolCallEvent)` returns typed intervention actions: `Proceed(reason=...)`, `Confirm(prompt=..., reason=...)`, `Guide(feedback=..., reason=...)`, `Deny(reason=...)`. |
| **V3** | Direct tool execution vs intervention hooks | `Strands Agent` runtime | Verified | Direct tool calls (`my_tool(...)`) outside `Agent.run` do NOT trigger intervention hooks. Therefore, `ScriptedExecutor` explicitly invokes `gate.evaluate(step.tool_name, results, policy)` before each tool execution, maintaining identical security invariants across both paths. |
| **V4** | Per-invocation context binding mechanism | `Agent.run` context provider | Verified | Bound via closure callable `context_provider: Callable[[], ItemContext]`. Sequential worker loop guarantees zero race conditions or leakage across items. |
| **V5** | `strands-decider serve` request/response format | HTTP `/v1/systemone` | Verified | `strands_decider.server.create_app` serves `POST /v1/systemone` accepting `SystemOneRequest` and returning `SystemOneResponse` with typed ChoiceAnswer / NoulAnswer. |
| **V6** | Bedrock model access & token pricing | Amazon Bedrock Runtime | Verified | Primary: `amazon.nova-micro-v1:0` ($0.035 in / $0.14 out per 1M tokens) |
| **V7** | CPU latency per question on user's machine | Decider 2B inference | Verified | Intel Core i5-1335U (4 threads): Q1 p50 = 13.59 s, item p50 = 27.20 s on ~400-token states. Triggers state-shrink rule (shrink max_tokens to 250). Second pass from SQLite cache = 0.00 ms. |

---

## 3. Package & Dependency Verifications
- **PyTorch CPU Wheel:** Installed `torch==2.14.1+cpu` from `https://download.pytorch.org/whl/cpu` (124 MB download), successfully avoiding multi-gigabyte CUDA bloat on CPU-only Windows host.
- **Model Checkpoint Architecture:** `StrandsAgents/strands-decider-2B-hobson-v21` loads on top of `Qwen/Qwen3.5-2B-Base` with a custom slot head and LoRA adapters. Weights cached locally in `C:\Users\AaronFrancis\.cache\huggingface\hub`.
- **Windows CPU Execution Characteristics:** Windows hosts lack CUDA and Triton kernels for `flash-linear-attention` (`fla`). As a result, HuggingFace transformers falls back to reference PyTorch execution for `chunk_gated_delta_rule`. Initial cold engine load takes ~18.6 s from disk cache, upcasting torso weights to fp32 (~5.7 GB memory footprint) to avoid slow CPU bf16 emulation.

---

## 4. Wording Experiment & CPU Latency Benchmark (Phase 4)
- **Script:** `scripts/wording_experiment.py` (results saved to `reports/wording_experiment.json`)
- **Variant 1 (Canonical Prompt):**
  - Q1 Text: *"Based on the item and the facts, which description best fits this contribution?"*
  - N1 Text: *"Does the text include concrete steps or code that would let a maintainer reproduce the problem?"*
  - **Results:** Avg Q1 Confidence: 0.3446; Predictions: `real_bug_report`, `low_effort`, `ready_for_review`; Item latency p50 = 27.20 s.
- **Variant 2 (Role-Focused Maintainer Prompt):**
  - Q1 Text: *"As an open-source maintainer, which classification best categorizes this contribution based strictly on the facts?"*
  - N1 Text: *"Does the item provide sufficient code, traceback, or reproduction steps to verify the issue?"*
  - **Results:** Avg Q1 Confidence: 0.3263; Predictions: biased towards `real_bug_report` with lower discernment; Item latency p50 = 25.00 s.
- **Engineering Decision:** Retain **Variant 1 (Canonical)** as the primary prompt set. Its confidence calibration is higher and classification across categories is more balanced.
- **State-Shrink Rule Applied:** Because per-item latency on ~400-token states exceeds the 10 s target on CPU, we apply the architecture's prescribed state-shrink rule: reduce `max_tokens` to 250 and `body_chars` to 800 in `policy.yaml`. Caching guarantees that repeat items incur 0.00 ms inference latency.
