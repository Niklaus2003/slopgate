# SlopGate — Plan Review and Verification Matrix

> **Purpose:** Detailed comparative review of `problem-statement.md`, `architecture.md`, and `implementation-plan.md`. This document highlights discrepancies, hidden dependencies, risk mitigations, concrete plan adjustments, verification paths for all unverified APIs, and essential configuration questions for the human supervisor.

---

## 1. Discrepancies and Ambiguities Across Project Documents

### 1.1 Action Vocabulary (`ActionKind` vs `proceed_soft`)
- **Observation:** `problem-statement.md` §8.2 defines an action "Proceed (soft)" specifically for `low_effort` items with HIGH confidence (applying `needs-more-detail` and posting an empathetic Bedrock-drafted reply, without closing). In contrast, `architecture.md` §5.1 defines enum `ActionKind` with four values: `PROCEED`, `CONFIRM`, `GUIDE`, `DENY`. In `architecture.md` §8.1 (`policy.yaml`), routing config maps `low_effort` to `proceed_soft`.
- **Resolution:** Explicitly define `ActionKind.PROCEED_SOFT = "proceed_soft"` in `models.py` (or represent it as `ActionKind.PROCEED` with a distinct `GateVerdict.is_soft = True` flag). In severity resolution, `PROCEED_SOFT` behaves with identical safety bounds as `PROCEED` (i.e. strictly disallowed from executing destructive tools like `close_item`).

### 1.2 Direct Tool Execution vs `InterventionHandler`
- **Observation:** `problem-statement.md` states all actions flow through `ConfidenceBandHandler`. `architecture.md` §6.6 acknowledges that in the Strands Agents SDK, intervention hooks might only intercept tool calls orchestrated by an LLM agent, not direct programmatic calls made by `ScriptedExecutor`.
- **Resolution:** Design decision D1 (framework-free core) solves this: `ConfidenceGate` is pure Python. `ScriptedExecutor` evaluates `gate.evaluate()` directly before dispatching routine tools, while `ConfidenceBandHandler` wraps the exact same gate for LLM agent calls. Both paths write identical audit receipts.

### 1.3 `DeciderResult.answer` Typing for `noul` Questions
- **Observation:** In `architecture.md` §5.1, `DeciderResult.answer` is typed as `str | bool`. However, §5.1 and §6.5 emphasize that `noul` questions must **never** be evaluated as a bare boolean because the decision depends on $P(\text{true})$ against asymmetric thresholds ($P \ge 0.85$ vs $P \le 0.15$).
- **Resolution:** While `DeciderResult.answer` can store `bool(p >= 0.5)` for display/logging convenience, `ConfidenceGate` and `bands.classify()` must operate strictly on `DeciderResult.probs["true"]`.

### 1.4 Offline Replay vs Repo File Index
- **Observation:** `state/facts.py` extracts `cited_paths_found` by comparing paths against `repo_index.py` (which queries Git tree / `git ls-files`). In offline replay mode (backtest and demo), a live Git clone might not exist locally for the sampled repository.
- **Resolution:** When `slopgate ingest --save data/samples/<name>.json` snapshots issue/PR data, it must also snapshot the repository file tree into `data/samples/<name>_tree.json`. This guarantees 100% offline reproducibility without requiring external Git clones.

---

## 2. Hidden Dependencies, Ordering Constraints, and Missing Steps

1. **Human Gold Labeling Timeline Bottleneck:**
   - *Current Plan:* Phase 8 Step 3 generates `data/gold/to_label.csv` for the human to hand-label ~60 items. If this happens only in Phase 8 (target Oct 20), waiting for human labeling will block the calibration report and threshold tuning.
   - *Mitigation:* Ingest and export `data/gold/to_label.csv` early during **Phase 3** (target Oct 16–17) so the human can review and label items asynchronously while the agent builds Phases 4 through 7.
2. **Windows Path and Line-Ending Normalization:**
   - *Observation:* The agent is executing on Windows with PowerShell. Git checkouts and Windows text processing often introduce `\r\n` (CRLF) and backslashes (`\`).
   - *Requirement:* All state text hashing must explicitly normalize `\r\n` -> `\n` (Edge case B15), and file path extractors must normalize Windows path separators to forward slashes `/` (Edge case B2) before hashing and lookup.
3. **PyTorch CPU Wheel Installation on Windows:**
   - Standard `pip install torch` on Windows can inadvertently pull multi-gigabyte CUDA binaries. Explicitly targeting the CPU wheel index (`https://download.pytorch.org/whl/cpu`) in Phase 1 ensures fast installation and keeps disk usage minimal.

---

## 3. Risks to Target Date (Oct 22) and Triage Cut Order

| Risk | Impact | Probability | Proactive Mitigation |
|---|---|---|---|
| **CPU Latency Overhead** | Decider takes > 10s per item on CPU | Medium | Enforce strict state truncation (<= 450 tokens); cascade questions with early exit; apply the state-shrink rule immediately if threshold exceeded. |
| **New API Incompatibilities** | Strands SDK or Decider import signatures differ from preliminary design | High | Verify in Phase 1 Step 1E before building application code. Keep the core framework-free so SDK differences only affect thin adapters. |
| **AWS Bedrock Quota / Credential Delays** | Bedrock access unconfigured or blocked | Low/Med | Implement `boto3` Converse fallback and local test mocks; utilize BudgetGuard with graceful degradation to pre-written markdown templates. |

### Strict Cut Order (If Behind Schedule)
If development lags behind schedule, non-essential elements will be dropped in this predetermined sequence:
1. **Drop P2:** Single-file HTML visual dashboard and second pattern (`patterns/grounding_check/`).
2. **Narrow Scope:** Reduce wording-variant backtest combinations from 3 variants to 1.
3. **Drop Alternative Backend:** Omit `HttpDecider` (`strands-decider serve`) and focus solely on the in-process `InProcessDecider`.
4. **Simplify Agent Layer:** If the full multi-turn Strands `LLMAgent` proves finicky, keep `reason_on_ambiguous` (single-shot Bedrock call) plus the review CLI.
5. **DO NOT CUT:** Reusable `patterns/confidence_band_handler/`, safety guarantees (close gating), offline backtest/calibration report, `ARTICLE.md`, or the `< 3 min` video script.

---

## 4. Verification Strategy for `architecture.md` §16 Items

| Item | Verification Objective | Target Phase | Verification Method & Source |
|---|---|---|---|
| **V1** | Multi-question batch API on single state (prefix reuse) in Strands Decider | **Phase 1E** | Write `scripts/smoke_decider.py` testing `StrandsDeciderModel`; inspect `strands_decider.modeling` signatures and measure forward pass latency for 1 vs 5 questions. |
| **V2** | Exact `InterventionHandler` import path, `before_tool_call` signature, and return types (`Proceed`, `Deny`, `Confirm`, `Guide`) | **Phase 1E** | Inspect `github.com/strands-labs/strands-decider` `examples/strands/` and the installed `strands-agents` package source code. |
| **V3** | Whether direct (non-LLM) tool calls pass through Strands interventions | **Phase 1E** | Execute a direct `tool.run()` or `agent.tools[0]()` call with an attached handler in a test script to check if `before_tool_call` fires. |
| **V4** | Per-invocation context binding mechanism in Strands Agents SDK | **Phase 1E** | Check `Agent.run()` / invocation parameters for per-session context dictionaries, or validate thread-safe / worker-scoped context provider closure. |
| **V5** | Request/response JSON schema for `strands-decider serve` | **Phase 1E / 4** | Launch `strands-decider serve --port 8000` locally; query OpenAPI `/docs` or send mock request via `httpx`. |
| **V6** | Enabled small Bedrock model ID and token pricing | **Phase 1E** | Query `boto3.client('bedrock').list_foundation_models()`; confirm access to e.g. `anthropic.claude-3-haiku-20240307-v1:0` or `amazon.nova-micro-v1:0` in the designated AWS region. |
| **V7** | CPU latency benchmark on user's local machine | **Phase 1E** | Execute 10 warm-up runs on a realistic 400-token issue state; log p50 and p95 latency to `docs/VERIFIED.md`. |

---

## 5. Concrete Plan Adjustments

```diff
--- a/docs/implementation-plan.md
+++ b/docs/implementation-plan.md
@@ -253,4 +253,6 @@
 ### Steps
 1. `ingest/github.py`: REST client, pagination, ETag cache, rate-limit backoff, token optional.
 2. `ingest/replay.py` and `slopgate ingest --save data/samples/<name>.json` to snapshot data once, so later work is offline and reproducible.
+   - Also snapshot repository file tree into `data/samples/<name>_tree.json` to enable 100% offline path verification.
+   - Export candidate ~60 items into `data/gold/to_label.csv` early so the human supervisor can label asynchronously.
 3. `state/repo_index.py`: file tree + symbol index, cached with TTL.
@@ -301,3 +303,4 @@
 ### Steps
 1. `models.py`: dataclasses/enums from `architecture.md` §5.1.
+   - Include `ActionKind.PROCEED_SOFT = "proceed_soft"` to cleanly distinguish soft-labeling from unconstrained proceed.
 2. `config.py`: load `.env` and `policy.yaml`; validate with pydantic; unknown keys are errors.
@@ -405,6 +408,35 @@
-# PHASE 10 — Demo, sandbox repo, optional HTML report
+# PHASE 10 — Next.js Interactive Dashboard, Demo Showcase, & API
+   - Lightweight Local API (`src/slopgate/api/server.py` via `slopgate serve`).
+   - Next.js Web App (`web/`):
+     * Page 1: Live Triage Simulator & Demo Playground (fact visualization, Decider confidence gauges, Bedrock drafts).
+     * Page 2: Maintainer Triage Inbox & Review Queue (receipt drawer, one-click approve/reject).
+     * Page 3: Calibration & Safety Analytics (visual charts for band accuracy, Bedrock cost savings, false-reject rates).
+   - Delivers compelling visual assets for the <3 min hackathon video and Builder Center article.
```

---

## 6. Confirmed Configuration Decisions (Locked In)

The following baseline parameters and environment configurations have been confirmed:

1. **Hardware Specifications:**
   - **CPU:** 13th Gen Intel Core i5-1335U (10 Cores: 2 P-cores + 8 E-cores, 12 Threads).
   - **RAM:** 15.69 GB (16 GB available).
   - **PyTorch Threading Setting:** `SLOPGATE_DECIDER_THREADS=4` (tuned to prioritize high-performance cores and prevent E-core synchronization thrashing).
   - **Python Environment:** Python 3.12.10 (64-bit on Windows).
2. **Bedrock Model Selection (Frugal & Free-Credit Optimized):**
   - **Primary Model:** `amazon.nova-micro-v1:0` ($0.035 / 1M input tokens, $0.14 / 1M output tokens).
   - **Secondary / Alternative Model:** `anthropic.claude-3-haiku-20240307-v1:0` ($0.25 / 1M input tokens, $1.25 / 1M output tokens).
   - **Strict Budget Policy:** `SLOPGATE_MAX_BEDROCK_CALLS=50` per run, `max_output_tokens=150` for replies.
   - **Zero-Cost Safeguard:** Full offline template fallback and mock client support during development so that zero paid API calls are ever incurred unless explicitly configured.
3. **Public Repository for Backtest:**
   - **Selected:** **`pallets/flask`** (150–200 closed issues/PRs; high label consistency: `duplicate`, `question`, `needs-repro`, `wontfix`).
   - Repository file tree and symbol index will be snapshotted to `data/samples/flask_tree.json` for 100% offline backtesting.
4. **License:**
   - **MIT License** selected.
5. **Interactive Frontend:**
   - Next.js Web Dashboard (`web/`) with live Triage Simulator, Maintainer Review Inbox, and Calibration Analytics charts added to Phase 10 alongside local API (`slopgate serve`).
6. **Execution Protocol:**
   - Planning and analysis phase complete. **Do not write code or install packages until the human explicitly gives the go-ahead.**
