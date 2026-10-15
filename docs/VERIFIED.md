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
| **V1** | Decider multi-question batch API (prefix reuse) | `strands_decider.modeling` | Pending (Phase 1E) | Measured in `scripts/smoke_decider.py` |
| **V2** | `InterventionHandler` class & return types (`Proceed`, `Deny`, `Confirm`, `Guide`) | `strands-agents` / `strands-decider/examples` | Pending (Phase 1E) | Inspected from repo source in `_refs/` |
| **V3** | Direct tool execution vs intervention hooks | `Strands Agent` runtime | Pending (Phase 1E) | Evaluated via direct call script |
| **V4** | Per-invocation context binding mechanism | `Agent.run` context provider | Pending (Phase 1E) | Closure / item context provider pattern |
| **V5** | `strands-decider serve` request/response format | HTTP `/v1/systemone` | Pending (Phase 1E) | Inspected via server startup |
| **V6** | Bedrock model access & token pricing | Amazon Bedrock Runtime | Verified | Primary: `amazon.nova-micro-v1:0` ($0.035 in / $0.14 out per 1M tokens) |
| **V7** | CPU latency per question on user's machine | Decider 2B inference | Pending (Phase 1E) | Measured in Phase 1E smoke test |

---

## 3. Package & Dependency Verifications
- **PyTorch CPU Wheel:** Installed `torch==2.14.1+cpu` from `https://download.pytorch.org/whl/cpu` (124 MB download), successfully avoiding multi-gigabyte CUDA bloat on CPU-only Windows host.
