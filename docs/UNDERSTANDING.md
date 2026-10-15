# SlopGate — Project Understanding and System Overview

> **Executive Summary:** SlopGate is an open-source, local-first, CPU-only triage gateway designed for open-source maintainers. It places a lightweight 1.9B parameter decision model (**Strands Decider 2B**) as a confidence-calibrated front door on the maintainer's personal computer. Routine contributions are triaged locally for free in seconds; **Amazon Bedrock** is called sparingly and safely only for nuanced reasoning on ambiguous cases and for generating constructive, empathetic responses. Crucially, SlopGate **never automatically closes any issue or pull request**.

---

## 1. What We Are Building and For Whom

### The Crisis in Open-Source Maintenance
Open-source maintainers face an unprecedented surge in low-effort, ungrounded, or synthetically churned bug reports and pull requests. Maintainer capacity has remained flat while contribution volume has exploded:
- `curl` shuttered its public HackerOne bug bounty in early 2026 after being overwhelmed by unverified security hallucinations.
- `tldraw` resorted to blanket-closing all external PRs.
- GitHub leadership and the ACM Technology Policy Council have highlighted that the volunteer infrastructure underpinning the software supply chain is strained to a breaking point.

### Why Existing Solutions Fail
1. **Blunt instruments:** Blanket bans, disabling issues, or auto-closing PRs discard genuine contributions and alienate enthusiastic newcomers.
2. **Costly cloud LLM triage:** Invoking a large commercial LLM on every incoming notification incurs unsustainable token costs and API latency for unfunded maintainers.
3. **Uncalibrated classifiers:** Conventional machine learning classifiers yield hard labels without meaningful confidence bounds, giving maintainers no way to distinguish a certain decision from a wild guess.

### Target Audience & The SlopGate Answer
SlopGate is built for the **solo maintainer or small core team** running on commodity developer hardware (a standard laptop CPU, no discrete GPU, minimal budget). 

By coupling:
- **Deterministic code facts** (symbol lookup, template validation, duplicate search),
- **Strands Decider 2B** (a fast, local, CPU-based scoring model that outputs calibrated confidence),
- A **confidence-band policy gate** (Proceed, Confirm, Guide, Deny), and
- **Amazon Bedrock** (reserved exclusively for synthesis and edge-case judgment),

SlopGate filters triage fatigue while maintaining maintainer oversight and ensuring psychological safety for new contributors.

---

## 2. End-to-End Data Flow

```
[ Incoming GitHub Issue / PR ]
              │
              ▼
    1. Ingestion Layer
       (GitHub REST API with ETag / Replay JSON Dump for reproducible testing)
              │
              ▼
    2. SQLite Queue (`items` table: status = 'queued')
              │
              ▼
    3. Worker Process (Drains queue oldest-first; long-lived process, loads model once)
              │
              ▼
    4. State Builder & Deterministic Fact Extraction
       - Truncates body/files to strict token budget (<= 450 tokens / ~1,800 chars)
       - Runs pure code fact extractors (cited symbols vs repo index, markdown parsing, BM25 duplicate score)
       - Computes stable state hash (sha256 over schema_version + state_text)
              │
              ▼
    5. Decider 2B Question Cascade (Local CPU Inference)
       - Cache check in SQLite: `(state_hash, question_id, question_text_hash, model_id)`
       - Q1 (Choice): Determines item kind (`real_bug_report`, `feature_request`, `low_effort`, etc.)
       - Early exit if Q1 is HIGH confidence and needs no follow-up
       - Conditional Follow-ups (N1–N5, Noul/Yes-No) batched in a single forward pass
              │
              ▼
    6. Policy & Confidence-Band Resolution
       - `bands.py`: Converts raw confidence/probability into HIGH, MEDIUM, LOW/UNCERTAIN
       - `gate.py`: Evaluates proposed actions against `policy.yaml` rules
       - `resolver.py`: Resolves conflicting verdicts via strict severity: `DENY > CONFIRM > GUIDE > PROCEED`
              │
              ├────────────────────────────────────────┬────────────────────────────────────────┐
              ▼                                        ▼                                        ▼
      [ Overall = PROCEED ]                  [ Overall = GUIDE / LOW ]               [ Gated Tool / CONFIRM ]
    Routine, high-confidence                 Ambiguous or low confidence              E.g., duplicate, security,
              │                                        │                              or ANY close_item call
              │                                        ▼                                        │
              │                               Amazon Bedrock Call                               │
              │                            `reason_on_ambiguous()`                              │
              │                         (Strict JSON schema, budget guard)                      │
              │                                        │                                        │
              ▼                                        ▼                                        ▼
    Scripted Executor                       Escalated Plan Generated                 Written to `pending_approvals`
    - Needs Bedrock draft?                             │                             - Awaiting human review
      -> Calls `draft_reply()`                         │                             - `slopgate review approve|reject`
    - Applies labels                                   └────────────────────────────────────────┤
    - Dry-run aware (no network unless `--live`)                                                ▼
              │                                                                      Maintainer Confirms Action
              ▼                                                                                 │
    7. Storage & Receipts                                                                       ▼
       - Writes immutable Decision Receipt (JSON + Markdown)                               Executed (or Dismissed)
       - Logs latency, tokens, cost, and decision path to SQLite
```

---

## 3. Technology Interconnection Map

| Component / Technology | Input / Source | Output / Destination | Boundary Data Contract | Ownership Module |
|---|---|---|---|---|
| **GitHub REST / Replay** | GitHub API / `data/samples/*.json` | SQLite `items` | Raw JSON dictionary -> normalized `Item` dataclass | `slopgate.ingest` |
| **Deterministic Extractors** | `Item` text + Repo Tree/Symbol Index | `Facts` dataclass | Extracted metrics: `(found, cited)`, `has_code_block`, `template_filled`, `BM25 candidate` | `slopgate.state.facts` |
| **State Builder** | `Item` + `Facts` | `State` dataclass | Compact formatted text block (cap <= 450 tokens), SHA-256 state hash | `slopgate.state.builder` |
| **Strands Decider 2B (CPU)** | `State.text` + `Question` list | `list[DeciderResult]` | Normalized confidence `(N*p_max - 1)/(N - 1)` for choice; `P(true)` for noul | `slopgate.decider` |
| **Confidence Policy** | `DeciderResult` + `policy.yaml` | `GateVerdict` & `ActionPlan` | Pure functional mapping: Band categorization (`HIGH`, `MEDIUM`, `LOW`) -> ActionKind (`PROCEED`, `CONFIRM`, `GUIDE`, `DENY`) | `slopgate.policy` |
| **Strands Agents SDK** | Tool invocation event | Tool execution or intercept | `ConfidenceBandHandler.before_tool_call` intercepts event and queries `ConfidenceGate` | `slopgate.agent.handler` |
| **Amazon Bedrock** | Escalated item context / draft prompt | Structured rationale / Markdown reply | Strict JSON (`suggested_label`, `rationale`) or text comment (<= 120 words). Budget guard monitored. | `slopgate.bedrock` |
| **Local Web API** | SQLite tables / triage pipeline | JSON HTTP responses | REST endpoints (`/api/items`, `/api/triage`, `/api/approvals`, `/api/stats`) | `slopgate.api.server` |
| **Next.js Dashboard** | Local Web API (`slopgate serve`) | Interactive UI in browser | Modern UI: Live Triage Simulator, Review Inbox, and Calibration Analytics charts | `web/` (Next.js app) |
| **SQLite Storage** | All pipeline events | SQLite DB / Reports | Normalized relational tables: `items`, `decisions`, `actions`, `pending_approvals`, `escalations`, `ground_truth` | `slopgate.store.db` |

---

## 4. Strands Decider 2B: Capabilities, Mathematics, and Limitations

### Model Identity & Architecture
Strands Decider 2B (`StrandsAgents/strands-decider-2B-hobson-v21`) is an open, specialized decision model developed by Strands Labs (AWS). It is built upon `Qwen3.5-2B-Base` with LoRA adapters and a pointer/readout scoring head. 

**What it DOES:**
- Performs option scoring across pre-specified candidate tokens in a single forward pass over the state.
- Operates on standard CPU hardware with low RAM overhead (~1.9B params).
- Reuses KV-cache / prefix tokens across multiple questions asked about the exact same state text.

**What it DOES NOT do:**
- It does **not** generate freeform natural language text.
- It does **not** read external tools, files, or Git history.
- It cannot replace generative agents; it acts as a fast, calibrated gatekeeper.

### Question Types & Confidence Mathematics
1. **`noul` (Yes/No Questions):**
   - Returns probability distribution over truth values: $P(\text{true}) \in [0.0, 1.0]$.
   - There is no separate confidence metric: the probability *is* the measure of uncertainty.
   - Thresholding:
     - Confident True: $P(\text{true}) \ge 0.85$
     - Confident False: $P(\text{true}) \le 0.15$
     - Uncertain (LOW band): $0.15 < P(\text{true}) < 0.85$
2. **`choice` (2 to $N$ discrete options):**
   - Evaluates normalized probabilities $p_1, p_2, \dots, p_N$ such that $\sum p_i = 1$.
   - Normalized confidence formula:
     $$\text{Confidence} = \frac{N \cdot p_{\max} - 1}{N - 1}$$
   - This scales confidence strictly from $0.0$ (uniform uncertainty, where $p_{\max} = 1/N$) to $1.0$ (absolute certainty, where $p_{\max} = 1.0$), ensuring identical threshold semantics across differing option counts.
3. **`score` (Ordered Likert-style levels):**
   - **STRICT PROHIBITION:** Upstream research demonstrates that `score` questions degrade significantly when applied out-of-distribution. **`score` questions are strictly prohibited in SlopGate.**

### Operating Limits & Design Accommodations
- **Benchmark Accuracy (~72% on JevBench):** The model is not infallible. Therefore, *calibration and confidence gating are the core product features*. If the model is not confident, it routes to Bedrock or maintainer review.
- **CPU Latency vs. State Length:** While short states evaluate in ~1.5s, inference time scales steeply at token lengths > 1,000. SlopGate enforces an aggressive token ceiling (<= 450 tokens) and cascades questions so routine items only evaluate Q1.
- **Question Wording Sensitivity:** Semantically identical questions can yield divergent confidence scores. SlopGate isolates questions into a single registry, hashes question strings to invalidate caches upon edit, and validates optimal wording via empirical backtesting.

---

## 5. Separation of the Reusable Pattern

A core hackathon submission requirement is a **clearly labeled, reusable Decider 2B decision pattern**. SlopGate isolates this capability into a standalone module:

```
patterns/confidence_band_handler/
├── README.md              # Self-contained "recipe card", quickstart, and non-SlopGate toy example
├── handler.py             # Strands InterventionHandler adapter
├── bands.py               # Pure mathematical confidence-band classification
├── gate.py                # Pure decision logic mapping (tool, decisions) -> GateVerdict
├── policy.example.yaml    # Declarative YAML policy configuration
├── example_agent.py       # Minimal standalone example gating a toy tool (e.g. `send_email`)
└── tests/                 # Dedicated unit test suite with zero SlopGate dependencies
```

### Decoupling Architecture
1. **Domain & Framework Agnostic Core:** `ConfidenceGate` and `bands.py` contain zero GitHub, issue, or SlopGate concepts. Any agent in any domain (e.g., finance, infrastructure, customer support) can evaluate arbitrary tools against Decider results.
2. **Clean Dependency Boundary:** The pattern directory **must not import from `src/slopgate/`**. SlopGate imports from the pattern, not vice versa.
3. **Thin Framework Adapter:** `ConfidenceBandHandler` merely bridges the pure `ConfidenceGate` into the Strands Agents SDK `InterventionHandler.before_tool_call` protocol.

---

## 6. The Safety and Ethics Model

SlopGate is explicitly engineered to prevent harm, bias, and automated disruption:

1. **The "Never Auto-Close" Invariant:**
   - The `close_item` tool call is hard-coded in Python to **never return `PROCEED`**.
   - Even if Decider 2B reports 100% confidence that an item is `low_effort` or invalid, the closing action is strictly routed to `CONFIRM` (requiring manual maintainer sign-off via `slopgate review`).
2. **Newcomer Protection & Constructive Empathy:**
   - Items assessed as `low_effort` receive a "soft proceed": a polite label (`needs-more-detail`) and a kind, actionable response drafted by Bedrock highlighting exactly what context or reproduction step is required.
   - Author history facts (e.g., account age, previous merge count) are **excluded from the state by default** to avoid algorithmic bias against first-time open-source contributors.
3. **Prompt Injection & Untrusted Data Containment:**
   - Issue/PR bodies are strictly treated as **untrusted data, never instructions**.
   - Deterministic facts are generated by deterministic code inspection, not from user assertions.
   - Prompts sent to Amazon Bedrock encapsulate contributor text inside explicit boundary delimiters (e.g. `<untrusted_item>...</untrusted_item>`) with explicit system instructions prohibiting execution of enclosed instructions.
   - Reply drafting and ambiguity reasoning calls possess no tool-execution capabilities.
4. **Failsafe Default (Dry-Run):**
   - All network mutations default to dry-run simulation. Real API writes are restricted to the maintainer's designated sandbox repository when `--live` is explicitly supplied.

---

## 7. Mapping Hackathon Requirements to Deliverables

| Hackathon Requirement | SlopGate Deliverable | Verification / Artifact |
|---|---|---|
| **Strands Decider 2B on AWS / Local** | In-process CPU Decider client executing Q1 choice + N1–N5 noul questions | `src/slopgate/decider/`, `scripts/smoke_decider.py` |
| **Amazon Bedrock Pairing** | Bedrock Runtime integration for constructive comment drafting (`draft_reply`) and ambiguous reasoning (`reason_on_ambiguous`) | `src/slopgate/bedrock/`, `scripts/smoke_strands.py` |
| **Reusable Decision Pattern** | `#policy` tagged standalone package: `patterns/confidence_band_handler/` | Recipe card README, standalone tests, toy agent example |
| **Written Article on AWS Builder Center** | Comprehensive technical article draft in `ARTICLE.md` with tags `#strands-decider-2b` and `#policy` | `ARTICLE.md` (architecture, backtest results, lessons) |
| **Public Repository & OSI License** | GitHub repository licensed under MIT / Apache-2.0, clean of secrets, comprehensive README | `LICENSE`, `.gitignore`, `README.md` |
| **Public Demo Video (< 3 minutes)** | Concise walkthrough script demonstrating end-to-end triage, high-confidence handling, ambiguity escalation, and review flow | `VIDEO_SCRIPT.md`, recorded demonstration video |
| **Interactive Showcase & UI** | Next.js interactive dashboard (`web/`) with live Triage Simulator, Maintainer Review Inbox, and visual calibration charts | `web/`, `src/slopgate/api/server.py` (`slopgate serve`) |
| **Timeline Compliance** | Oct 16 – Oct 23, 2026 window; submission targeted for **Oct 22** with buffer | `docs/implementation-plan.md` progress tracker |

---

## 8. Five-Minute Engineer Narrative

> "Imagine you run a popular open-source project. Every morning you wake up to dozens of notifications: vague one-line bug reports, duplicate questions, and automated pull requests. You don't want to shut down the community, but you don't have hours to triage, and you can't afford hundreds of dollars in cloud LLM API bills.
> 
> SlopGate solves this by running a calibrated front door right on your laptop CPU. When a contribution arrives, lightweight Python code extracts key facts: Did they include code blocks? Did they cite actual files that exist in the repo? Is this a duplicate of an existing issue? 
> 
> We pass this concise context to **Strands Decider 2B**, an ultra-lightweight decision model from Strands Labs that runs locally on your CPU for free. In a split second, it classifies the item and tells us mathematically how confident it is.
> 
> If it's highly confident it's a valid bug report with reproduction steps, SlopGate applies a `triaged` label instantly. If it's low effort, SlopGate never closes it; instead, it asks **Amazon Bedrock** to draft a kind, encouraging comment explaining exactly what information is missing. If the item is ambiguous or confidence is low, it halts and flags it for your approval in a local review queue. And importantly: SlopGate will never auto-close any issue or PR without your explicit command.
> 
> You get effortless, zero-cost triage; your contributors get fast, respectful feedback; and the entire decision-gating logic is packaged as a reusable, plug-and-play pattern for any Strands agent."
