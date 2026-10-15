# SlopGate — Architecture

**Companion to `problem-statement.md`.** That file explains *why* and *what*. This file explains *how*: process model, module boundaries, data model, control flow, interfaces, failure handling, and testing. Read `problem-statement.md` first.

**Convention:** anything marked **`VERIFY`** touches a new third-party API (Strands Decider, Strands Agents SDK `InterventionHandler`, Bedrock model IDs). The code sketches below are *design intent*, not confirmed library signatures. Read the official examples, run a small experiment, then adapt.

---

## 1. Key architectural decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | **Framework-free core, thin framework adapters.** Decision logic lives in pure Python (`ConfidenceGate`); the Strands `InterventionHandler` is a ~30-line adapter around it. | Testable without a model or SDK; the reusable pattern survives SDK changes; others can adopt the core in any agent framework. |
| D2 | **Single worker process, model loaded once.** | A 1.9B model is RAM-heavy; multiple processes would duplicate it. CPU inference is already the bottleneck. |
| D3 | **Async-by-queue, not request/response.** | CPU latency is seconds, not milliseconds. A SQLite-backed queue decouples ingestion from decisioning. |
| D4 | **Deterministic facts feed the fuzzy decision.** | The 2B model should judge *grounding* from supplied evidence, not recall or look things up. Also keeps state short for CPU. |
| D5 | **Question cascade with early exit.** | CPU cost scales with questions; most items need 1–3. |
| D6 | **Most-restrictive-wins action resolution.** | Safety: if any decision says Confirm/Deny, that wins over Proceed. |
| D7 | **Routine items → scripted executor; hard items → LLM agent (Bedrock).** | Decider does the cheap routine work; the generative agent only runs where judgment is needed. This is the "hybrid agent" story. |
| D8 | **Dry-run is the default.** Writes require `--live` plus a token. | Never act on real third-party repos by accident. |
| D9 | **Every decision is persisted with its evidence.** | Receipts, calibration report, and debugging all read the same tables. |
| D10 | **Untrusted text is data, never instructions.** | Issue bodies can contain prompt-injection. See section 13. |

---

## 2. System context

```
                         ┌─────────────────────────────────────────────────────────┐
                         │                   Maintainer's laptop                   │
                         │                    (CPU only, local)                    │
                         │                                                         │
 GitHub REST API ───────►│  Ingestor ─► SQLite ─► Worker                           │
 (public repo; token     │     ▲        (queue,     │                              │
  optional; write only   │     │         state,     ├─► Strands                    │
  in --live)             │     │         receipts)  │   Decider 2B                 │
        ▲                │  replay JSON             │   (in-process, CPU)          │
        │ labels/comments│  (backtest/demo)         │                              │
        └────────────────┼──────────────────────────┼─► Agent layer                │
                         │                          │   + ConfidenceBandHandler    │
                         │                          │                              │
                         │  Local API (`serve`) ◄───┴─► Review CLI / report        │
                         │          ▲                                              │
                         │          │ JSON endpoints                               │
                         │          ▼                                              │
                         │  Next.js Frontend                                       │
                         │  - Live Triage Simulator                                │
                         │  - Review Inbox & Approvals                             │
                         │  - Calibration Analytics                                │
                         └──────────────────────────┬──────────────────────────────┘
                                                    │ only for drafts & hard cases
                                                    ▼
                                             Amazon Bedrock
                                             (small model, budget-capped)
```

External dependencies and their failure modes are in section 11.

---

## 3. Process and concurrency model

- **One long-lived worker process** (`slopgate run`). On start: load config → open SQLite → load Decider **once** → warm up with one dummy question → begin draining the queue.
- **Worker loop is sequential** for Decider calls (CPU-bound, one model instance). Do not parallelize inference.
- **I/O may be concurrent** (GitHub fetch, Bedrock calls) via a small thread pool or `asyncio`, but keep it simple: prefetch/ingest runs in a separate command (`slopgate ingest`) or a background thread; Bedrock calls happen inline and are capped by the budget guard.
- **Threads:** set torch/OMP threads to the physical core count from config (`decider.threads`). Document the chosen value in the calibration report header.
- **Backpressure:** the queue is a table; the worker pulls `status='queued'` oldest-first. No in-memory unbounded buffers.
- **Graceful shutdown:** on SIGINT, finish the current item, commit, exit. Items in `processing` older than a timeout are reset to `queued` at next start (crash recovery).

Item lifecycle:

```
queued ──► processing ──► decided ──► (executed | pending_approval | flagged)
   ▲            │                             │
   └── timeout──┘                    approved/rejected by maintainer
                                              ▼
                                       executed | dismissed
```

---

## 4. Repository layout

```
slopgate/
├─ README.md
├─ LICENSE                      # MIT or Apache-2.0
├─ pyproject.toml / requirements.txt
├─ policy.example.yaml
├─ .env.example                 # no secrets committed
├─ src/slopgate/
│  ├─ cli.py                    # ingest | run | review | backtest | report | demo
│  ├─ config.py                 # load/validate settings + policy.yaml (pydantic or dataclasses)
│  ├─ models.py                 # dataclasses shared across modules (section 5)
│  ├─ ingest/
│  │  ├─ github.py              # REST client, ETag cache, rate-limit backoff
│  │  └─ replay.py              # read saved JSON dumps (backtest/demo)
│  ├─ state/
│  │  ├─ builder.py             # compact state string + token cap
│  │  ├─ facts.py               # deterministic fact extractors
│  │  ├─ repo_index.py          # file tree + symbol index cache
│  │  └─ similarity.py          # TF-IDF/BM25 duplicate candidates
│  ├─ decider/
│  │  ├─ client.py              # DeciderClient protocol + backends
│  │  ├─ questions.py           # typed question registry (single source of truth)
│  │  └─ cascade.py             # question ordering, early exit
│  ├─ policy/
│  │  ├─ bands.py               # pure: probabilities → Band
│  │  ├─ gate.py                # ConfidenceGate: decisions → GateVerdict (pure)
│  │  └─ resolver.py            # most-restrictive-wins, action plan
│  ├─ agent/
│  │  ├─ tools.py               # Strands tools (dry-run aware)
│  │  ├─ handler.py             # ConfidenceBandHandler adapter (VERIFY)
│  │  ├─ executor.py            # scripted executor for routine items
│  │  └─ llm_agent.py           # Bedrock-driven agent for hard items
│  ├─ bedrock/
│  │  ├─ client.py              # invoke wrapper, retries
│  │  ├─ prompts.py             # prompt templates (data-delimited)
│  │  ├─ escalate.py            # draft_reply, reason_on_ambiguous
│  │  └─ budget.py              # budget guard
│  ├─ store/
│  │  ├─ db.py                  # SQLite access, migrations
│  │  └─ schema.sql
│  ├─ report/
│  │  ├─ receipts.py            # JSON + Markdown receipts
│  │  ├─ calibration.py         # accuracy by band, coverage, false-reject, latency, cost
│  │  └─ html.py                # optional single-file report
│  ├─ api/
│  │  └─ server.py              # lightweight local FastAPI / REST API (slopgate serve)
│  └─ backtest/
│     ├─ runner.py              # replay → decisions → metrics
│     └─ baseline.py            # Bedrock-only baseline on same items
├─ web/                         # Next.js interactive frontend dashboard
│  ├─ app/                      # Next.js App Router (pages: simulator, review inbox, stats)
│  ├─ components/               # UI components (ConfidenceGauge, ReceiptDrawer, FactCard)
│  ├─ styles/                   # design system tokens, dark theme, glassmorphism CSS
│  ├─ package.json
│  └─ README.md
├─ patterns/
│  └─ confidence_band_handler/  # THE reusable asset (standalone, minimal deps)
│     ├─ README.md  handler.py  bands.py  policy.example.yaml
│     ├─ example_agent.py  tests/
├─ data/
│  ├─ samples/                  # replay JSON dumps (public data only)
│  └─ gold/                     # hand-labeled subset
├─ demo/                        # seeded sandbox-repo fixtures + script
├─ tests/                       # unit + integration (section 14)
├─ ARTICLE.md                   # Builder Center draft
└─ VIDEO_SCRIPT.md
```

**Dependency rule:** `patterns/confidence_band_handler/` must not import from `src/slopgate/`. The main app may import from the pattern or vendor-copy it. This keeps the pattern truly reusable.

---

## 5. Data model

### 5.1 In-memory types (`models.py`; design sketch)

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Optional

ItemType = Literal["issue", "pull_request"]
QType = Literal["choice", "noul"]

class Band(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"          # for noul: UNCERTAIN maps to LOW

class ActionKind(str, Enum):  # mirrors the handler's vocabulary (VERIFY names)
    PROCEED = "proceed"
    CONFIRM = "confirm"
    GUIDE = "guide"
    DENY = "deny"

@dataclass(frozen=True)
class Item:
    repo: str
    number: int
    type: ItemType
    title: str
    body: str
    created_at: str
    files: list[str] = field(default_factory=list)      # PRs
    additions: int = 0
    deletions: int = 0
    ci_status: str = "unknown"
    author_login: Optional[str] = None                   # NOT used in state by default
    raw: dict = field(default_factory=dict)

@dataclass(frozen=True)
class Facts:
    cited_paths_found: tuple[int, int]        # (found, cited)
    has_code_block: bool
    has_repro_heading: bool
    template_filled: tuple[int, int]
    links_to_issue: list[int]
    ci_status: str
    candidate_duplicate: Optional[tuple[int, float]]     # (number, similarity)
    contributing_excerpt: Optional[str]

@dataclass(frozen=True)
class State:
    text: str                  # what Decider sees
    hash: str                  # sha256 over text + schema_version
    approx_tokens: int
    facts: Facts

@dataclass(frozen=True)
class Question:
    id: str                    # "Q1_issue_kind", "N1_repro", ...
    qtype: QType
    text: str
    options: tuple[str, ...] = ()               # choice only
    descriptions: dict[str, str] = field(default_factory=dict)
    applies_to: tuple[ItemType, ...] = ("issue", "pull_request")

@dataclass(frozen=True)
class DeciderResult:
    question_id: str
    qtype: QType
    answer: str | bool                 # choice label, or noul bool at 0.5 (do not use bool alone for gating)
    probs: dict[str, float]            # option → p ; noul: {"true": p, "false": 1-p}
    confidence: Optional[float]        # choice only (normalised); None for noul
    latency_ms: float
    model_id: str
    from_cache: bool

@dataclass(frozen=True)
class GateVerdict:
    question_id: str
    band: Band
    action: ActionKind
    reason: str

@dataclass
class ActionPlan:
    steps: list["PlannedToolCall"]      # tool name + args
    overall: ActionKind                 # most restrictive across verdicts
    needs_bedrock_draft: bool
    needs_bedrock_reasoning: bool
    receipt_notes: list[str]
```

**Rules:** `noul` answers are never reduced to a bare bool for gating; use the probability `P(true)` against the policy's `true_at_least` / `false_at_most` thresholds.

### 5.2 State hash

`hash = sha256(schema_version + "\n" + state.text)`. Bump `schema_version` whenever the state format or fact extractors change, so cached decisions invalidate. Cache key for decisions: `(state_hash, question_id, question_text_hash, model_id)`.

### 5.3 SQLite schema (`store/schema.sql`)

```sql
CREATE TABLE items (
  id INTEGER PRIMARY KEY,
  repo TEXT NOT NULL, number INTEGER NOT NULL, type TEXT NOT NULL,
  title TEXT, created_at TEXT, state_text TEXT, state_hash TEXT,
  status TEXT NOT NULL DEFAULT 'queued',   -- queued|processing|decided|executed|pending_approval|flagged|dismissed|error
  processing_started_at TEXT,
  raw_json TEXT NOT NULL,
  UNIQUE(repo, number)
);

CREATE TABLE decisions (
  id INTEGER PRIMARY KEY,
  item_id INTEGER NOT NULL REFERENCES items(id),
  question_id TEXT NOT NULL, qtype TEXT NOT NULL,
  question_text_hash TEXT NOT NULL,
  answer TEXT, probs_json TEXT, confidence REAL,
  band TEXT, gate_action TEXT, gate_reason TEXT,
  latency_ms REAL, model_id TEXT, from_cache INTEGER DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_decisions_cache ON decisions(question_id, question_text_hash, model_id);

CREATE TABLE actions (
  id INTEGER PRIMARY KEY,
  item_id INTEGER NOT NULL REFERENCES items(id),
  tool TEXT NOT NULL, args_json TEXT,
  handler_result TEXT,                     -- proceed|confirm|guide|deny
  executed INTEGER DEFAULT 0, dry_run INTEGER DEFAULT 1,
  idempotency_key TEXT UNIQUE,             -- e.g. repo#num:label:needs-info
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE pending_approvals (
  id INTEGER PRIMARY KEY,
  item_id INTEGER NOT NULL REFERENCES items(id),
  proposed_plan_json TEXT NOT NULL,
  receipt_md TEXT,
  status TEXT DEFAULT 'pending',           -- pending|approved|rejected
  decided_at TEXT
);

CREATE TABLE escalations (
  id INTEGER PRIMARY KEY,
  item_id INTEGER NOT NULL REFERENCES items(id),
  purpose TEXT NOT NULL,                   -- draft_reply|reason_on_ambiguous|baseline
  bedrock_model TEXT, tokens_in INTEGER, tokens_out INTEGER,
  latency_ms REAL, est_cost_usd REAL, output_text TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE ground_truth (
  item_id INTEGER PRIMARY KEY REFERENCES items(id),
  label TEXT NOT NULL, source TEXT NOT NULL   -- 'proxy' | 'gold'
);
```

---

## 6. Module designs

### 6.1 Ingestion (`ingest/`)
- `GitHubSource.fetch(repo, since) -> Iterator[Item]`: REST, pagination, ETag/If-None-Match caching in SQLite, honors `X-RateLimit-*`, exponential backoff, optional token from env.
- `ReplaySource.fetch(path) -> Iterator[Item]`: reads a saved JSON dump. **Backtest and demo use only this.** Provide `slopgate ingest --save data/samples/x.json` to snapshot live data once.
- Upsert on `(repo, number)`; re-ingesting an edited item that changes `state_hash` re-queues it.

### 6.2 State building (`state/`)
- `repo_index.py` builds a cached file tree (`git ls-files` on a shallow clone, or GitHub tree API) and a lightweight symbol index (regex/ctags-style). Rebuilt on a TTL.
- `facts.py` has one small pure function per fact; each is unit-tested.
- `builder.py` assembles the text in the exact format of `problem-statement.md` §6.1, truncating the body first, then file list, never the facts. Reports `approx_tokens`; raises a metric (not an error) when truncation occurs.
- **Author-history facts are not computed unless** `policy.state.include_author_history: true`.

### 6.3 Decider client (`decider/client.py`)

```python
class DeciderClient(Protocol):
    model_id: str
    def ask(self, state: State, questions: list[Question]) -> list[DeciderResult]: ...
```

Backends:
- `InProcessDecider`: wraps `strands_decider.modeling.StrandsDeciderModel` (**VERIFY** the batch/“many questions about one state” API so the state prefix is read once).
- `HttpDecider`: calls `strands-decider serve` (**VERIFY** request/response shape; the LiteLLM docs for `/v1/systemone` describe a `choices` / `levels` format with `instructions` per question).
- `FakeDecider`: deterministic, scripted by question id and substring rules. **Used by all unit tests and CI.** Must never download a model.

Wrapper responsibilities: cache lookup before inference, per-question latency timing, normalize outputs into `DeciderResult`, catch exceptions → raise `DeciderUnavailable`.

### 6.4 Question registry & cascade (`decider/`)
- `questions.py` is the only place question text/options live. Each question has a stable `id`; changing wording changes `question_text_hash` and invalidates cache automatically.
- `cascade.py`:

```
def run_cascade(item, state, decider, policy):
    results = []
    q1 = pick_q1(item.type)
    r1 = decider.ask(state, [q1])[0]; results.append(r1)
    band1 = bands.classify(q1, r1, policy)

    followups = select_followups(item, state.facts, r1, band1, policy)   # table in problem-statement §7
    if followups:
        results += decider.ask(state, followups)       # one call → state read once
    return results
```

  - **Early exit:** if `select_followups` returns nothing because Q1 is HIGH and the outcome needs no more evidence, stop.
  - Follow-ups depend only on Q1's label and facts, so they can be asked in **one** batched call.

### 6.5 Policy layer (`policy/`) — pure, no I/O

- `bands.classify(question, result, policy) -> Band`:
  - choice: use normalized `confidence` vs `choice.high_at_least`, `choice.medium_at_least`.
  - noul: `P(true) ≥ true_at_least` → HIGH(true); `≤ false_at_most` → HIGH(false); else LOW.
- `gate.ConfidenceGate.evaluate(tool_name, results, policy) -> GateVerdict`: given a *proposed tool call* and the decisions relevant to it, returns Proceed/Confirm/Guide/Deny per the rule table. This is the heart of the reusable pattern.
- `resolver.resolve(verdicts) -> ActionPlan`: most-restrictive-wins. **Severity order: `DENY > CONFIRM > GUIDE > PROCEED`.**
- **Hard rules in code, not config** (cannot be loosened by `policy.yaml`):
  - `close_item` → never `PROCEED`.
  - `security_report` → at least `CONFIRM`.
  - Any tool not listed in policy → `CONFIRM`.

### 6.6 Agent layer (`agent/`)

Two execution paths, chosen per item by the plan:

```
                        ┌─ overall == PROCEED, no reasoning needed ─► ScriptedExecutor
 Cascade → Plan ────────┤
                        └─ overall in {GUIDE, CONFIRM-with-reasoning} ─► LLMAgent (Bedrock)
```

- **Tools (`tools.py`)** — Strands tools: `apply_label`, `post_comment`, `request_info_comment`, `flag_for_maintainer`, `close_item`. Every write tool checks `ctx.dry_run`; in dry-run it records the intended call and returns a simulated success. Every tool computes an `idempotency_key` and skips if already executed.
- **`ConfidenceBandHandler` (`handler.py`)** — the adapter:

```python
# DESIGN SKETCH. VERIFY exact base class, hook signature, and return types
# against strands-decider/examples/strands/ and the Strands Agents docs.
class ConfidenceBandHandler(InterventionHandler):
    def __init__(self, gate: ConfidenceGate, context_provider, policy):
        self.gate, self.ctx_provider, self.policy = gate, context_provider, policy

    def before_tool_call(self, event):               # signature: VERIFY
        ctx = self.ctx_provider()                     # current item's decisions (see below)
        verdict = self.gate.evaluate(event.tool_name, ctx.results, self.policy)
        record_receipt(ctx, event, verdict)
        if verdict.action is ActionKind.PROCEED: return Proceed()
        if verdict.action is ActionKind.CONFIRM: return Confirm(verdict.reason)
        if verdict.action is ActionKind.GUIDE:   return Guide(verdict.reason)
        return Deny(verdict.reason)
```

  - **How the handler knows the current item (`VERIFY`):** prefer whatever per-invocation state mechanism the SDK offers; otherwise bind a small mutable `ItemContext` via closure (`context_provider`) set by the worker before each agent invocation. Single-threaded worker makes this safe.
  - **Scripted executor and the handler (`VERIFY`):** if the SDK routes *direct* tool invocations (not LLM-chosen) through interventions, use that. If not, the executor calls `gate.evaluate(...)` explicitly before each tool and the handler is exercised in the LLM path. The core logic is identical either way (decision D1). Document which route you found.
- **`llm_agent.py`**: a Strands `Agent` with a Bedrock model, the tools above, the `ConfidenceBandHandler`, and a system prompt that includes the receipt (not the raw untrusted text unless needed, and delimited as data). It runs only for escalated items, so Bedrock cost stays bounded.

### 6.7 Bedrock layer (`bedrock/`)
- `client.py`: `invoke(model_id, system, messages, max_tokens) -> (text, tokens_in, tokens_out, latency)`; retries with jitter on throttling; model id and region from env (**VERIFY** the enabled small model).
- `budget.py`: `BudgetGuard` tracks calls/tokens per run and per day; `allow(purpose) -> bool`; when denied, callers degrade (section 11).
- `escalate.py`:
  - `draft_reply(item, receipt, template_hint) -> str`
  - `reason_on_ambiguous(item, facts, decider_probs) -> {suggested_label, rationale}` (JSON-only output, validated; invalid JSON → treated as failure → flag for maintainer).
- `prompts.py`: all prompts as versioned templates; untrusted fields are wrapped in explicit delimiters (section 13).

### 6.8 Storage, receipts, reporting
- `db.py`: thin repository functions; all writes in transactions; WAL mode.
- `receipts.py`: renders from `decisions`+`actions`+`escalations` for one item (JSON + Markdown); no logic duplicated from the gate (it stores `gate_reason`).
- `calibration.py`: computes metrics purely from tables (so a backtest report can be regenerated without re-running the model): accuracy per band, coverage, escalation rate, **false-reject rate**, p50/p95 latency, Bedrock tokens/cost vs baseline, header with machine specs.

### 6.9 Review flow (`slopgate review`)
- Lists `pending_approvals` with the receipt; `approve <id>` executes the stored plan (still dry-run unless `--live`), `reject <id>` dismisses. `close_item` can only execute via this path.

### 6.10 Local Web API & Next.js Frontend Dashboard (`api/` and `web/`)
- **Backend API (`api/server.py`):** Exposed via `slopgate serve [--port 8000]`. Lightweight REST endpoints over SQLite and pipeline runners:
  - `GET /api/items`: query items with filters (`status`, `band`, `repo`).
  - `GET /api/items/{id}/receipt`: fetch JSON & formatted Markdown receipt.
  - `POST /api/triage`: run real-time triage for arbitrary issue/PR text or demo presets (executes StateBuilder → Decider Cascade → Policy Gate → optional Bedrock escalation).
  - `POST /api/approvals/{id}/action`: maintainer approval/rejection of pending action plans.
  - `GET /api/stats/calibration`: aggregate calibration metrics (accuracy per band, coverage, latency percentiles, Bedrock token costs vs baseline).
  - `GET /api/demo/fixtures`: list pre-seeded synthetic demo items.
- **Next.js Frontend (`web/`):**
  - **Triage Simulator:** interactive playground to paste contributions or select seeded presets, with visual meters for facts, Decider confidence, and Bedrock drafts.
  - **Maintainer Review Inbox:** intuitive card/drawer UI to approve or reject pending actions with full audit receipt.
  - **Calibration & Safety Charts:** visual analytics of accuracy per band, false-reject rates, and cost savings vs Bedrock baseline.

---

## 7. Control flows

### 7.1 Batch flow (routine item)

```
worker: pop item (status=processing)
  → build State (facts, hash)
  → cascade: Decider.ask Q1 → (maybe) follow-ups     [cache check first]
  → bands.classify each → gate/resolver → ActionPlan
  → overall == PROCEED?
       ├─ needs_bedrock_draft? → draft_reply (budget guard) → attach text
       └─ ScriptedExecutor runs tools (dry-run aware, idempotent)
  → write receipt; status=executed
```

### 7.2 Escalation flow (hard item)

```
plan.overall in {GUIDE, CONFIRM}
  → reason_on_ambiguous (Bedrock) → suggested label + rationale
  → (optional) LLMAgent invoked with tools; handler gates every call
  → final plan → pending_approvals; status=pending_approval
  → maintainer: slopgate review approve|reject
```

### 7.3 Backtest flow

```
ReplaySource → for each item: state → cascade → plan (NO writes, ever)
  → compare plan/label to ground_truth → store
  → baseline.py: same items through Bedrock-only classification (capped sample)
  → calibration.py → report.md / report.html
```

### 7.4 Interactive Web Flow (Next.js + `slopgate serve`)

```
User in Browser (http://localhost:3000)
  │  (Pastes issue/PR text or picks a demo preset)
  ▼
POST /api/triage ──► api/server.py
                       │
                       ├─► StateBuilder + Facts (code extractors)
                       ├─► InProcessDecider.ask (Q1 + N1-N5 cascade)
                       ├─► PolicyGate (bands + resolver)
                       └─► (If Guide/ambiguous) Bedrock escalate
                       │
                       ▼
Returns JSON: { facts, decisions, confidence, band, action, receipt, bedrock_draft }
  │
  ▼
Next.js UI renders real-time:
  - Fact extraction badges
  - Decider 2B confidence meter (with color-coded bands)
  - Action routing badge (Proceed / Confirm / Guide / Deny)
  - Bedrock response / draft comment
```

---

## 8. Configuration

### 8.1 `policy.yaml` (validated at startup; unknown keys are errors)

```yaml
version: 1
repo: owner/name

state:
  max_tokens: 450
  body_chars: 1200
  include_author_history: false      # opt-in; off by default (protect newcomers)

bands:
  choice: { high_at_least: 0.80, medium_at_least: 0.50 }
  noul:   { true_at_least: 0.85, false_at_most: 0.15 }

duplicate:
  similarity_min: 0.55

routing:                               # kind -> behavior; hard rules in code override this
  real_bug_report:   { high: proceed, medium: confirm, low: guide }
  support_question:  { high: proceed, medium: confirm, low: guide }
  likely_duplicate:  { high: confirm, medium: confirm, low: guide }
  low_effort:        { high: proceed_soft, medium: confirm, low: guide }
  security_report:   { high: confirm, medium: confirm, low: confirm }   # floor enforced in code
  ready_for_review:  { high: proceed, medium: confirm, low: guide }

labels:
  triaged: triaged
  needs_info: needs-info
  question: question
  low_effort: needs-more-detail
  ready: ready-for-review

templates:                             # used without Bedrock when possible
  support_question: templates/support_question.md
  needs_repro: templates/needs_repro.md

tools_gated:
  apply_label:        { requires: [Q1] }
  post_comment:       { requires: [Q1] }
  close_item:         { always: confirm }      # redundant with code rule, kept for clarity
```

### 8.2 `.env` (never committed)

```
GITHUB_TOKEN=            # optional for read; write token only for demo sandbox
AWS_REGION=
BEDROCK_MODEL_ID=
# AWS credentials via standard env/profile, or a Bedrock API key
SLOPGATE_DRY_RUN=1
SLOPGATE_MAX_BEDROCK_CALLS=50
SLOPGATE_MAX_OUTPUT_TOKENS=300
SLOPGATE_DECIDER_THREADS=
```

---

## 9. Performance budget (targets to measure, not promises)

| Stage | Target on a typical laptop CPU | Notes |
|---|---|---|
| State build | < 50 ms | pure Python; index cached |
| Decider Q1 (≈400-token state) | ~1–3 s | measure on this machine; reported ~1.6 s/question on an 8-thread Xeon |
| Batched follow-ups (2–3 noul) | ~1–3 s | state prefix reuse (**VERIFY** it is exercised) |
| Bedrock draft (when needed) | 1–4 s network-bound | not CPU |
| End-to-end routine item | ~3–8 s | if > ~10 s, shrink state (see problem-statement §11) |

Record actual numbers per stage in `decisions.latency_ms` and `escalations.latency_ms`.

---

## 10. Observability
- Structured logs (JSON lines): `item`, `stage`, `latency_ms`, `from_cache`, `band`, `action`. No raw item bodies at INFO level.
- Per-run summary printed at exit: items processed, cache hits, escalations, Bedrock tokens/cost, p50/p95 per-item seconds.
- Metrics needed for the article come from SQLite, not logs.

---

## 11. Failure handling and graceful degradation

| Failure | Behavior |
|---|---|
| Decider load/inference error | Mark item `flagged`; receipt says "decision unavailable"; **never** guess an action. Worker continues. |
| State exceeds token cap | Truncate body → files; log truncation; never truncate facts. |
| Cache corruption | Ignore cache, recompute, log. |
| Bedrock throttled/unavailable | Retry with jitter (bounded); then degrade: use template reply if available, else `flag_for_maintainer`. |
| Budget guard exhausted | Same degradation; receipt notes "budget cap reached". |
| Bedrock returns invalid JSON (reasoning call) | Treat as failure → flag; do not parse leniently. |
| GitHub rate limit | Honor reset time; backoff; ingestion pauses, worker keeps draining the queue. |
| GitHub write fails (live) | Record failure in `actions`; leave idempotency key unset; surface in review. |
| Crash mid-item | On restart, `processing` items older than timeout return to `queued`; idempotency keys prevent double actions. |

---

## 12. Idempotency and re-runs
- `idempotency_key = f"{repo}#{number}:{tool}:{normalized_args}"`. Tools skip if the key exists with `executed=1`.
- Re-ingesting an unchanged item is a no-op. A changed item (new `state_hash`) is re-queued; previous receipts are retained and marked superseded.
- The backtest never writes to `actions` with `executed=1`.

---

## 13. Security and safety design

**Untrusted input.** Issue/PR text may contain prompt-injection aimed at the classifier or at Bedrock. Mitigations:
1. **Facts come from code**, not from the text, so hostile text can't forge grounding evidence.
2. **Bedrock prompts delimit untrusted text** (e.g., `<untrusted_item>…</untrusted_item>`) and instruct the model to treat it as data only; the system prompt states that nothing inside the delimiters is an instruction.
3. **`draft_reply` and `reason_on_ambiguous` have no tools.** Only the escalated `LLMAgent` has tools, and every tool call passes through the handler.
4. **Blast radius is capped by policy:** the worst case for a manipulated decision is a wrong label or a `Confirm` queue entry; `close_item` cannot run unattended.
5. Output validation: replies are length-capped and scanned for URLs not in an allowlist (CONTRIBUTING/docs links); suspicious drafts are flagged, not posted.

**Secrets:** env only; `.env` git-ignored; a pre-commit/CI check greps for key patterns.

**Privacy:** the model runs locally; only escalated item text goes to Bedrock. Published examples in the article/repo must be anonymized or from public data with usernames removed.

**Fairness:** author identity excluded from state by default; false-reject rate is a headline metric; `low_effort` produces a soft label and a helpful reply, never a rejection.

---

## 14. Testing strategy

| Layer | Approach |
|---|---|
| `bands`, `gate`, `resolver` | Pure unit tests with table-driven cases, including every hard rule (e.g., `close_item` never Proceed at any confidence). |
| `facts`, `builder` | Unit tests on fixture items; token-cap truncation order; stable hashing. |
| Cascade | `FakeDecider` scripted outputs; verify early exit and batching. |
| Handler adapter | Test with a minimal fake agent/event object; assert each verdict maps to the right return type (**VERIFY** types first). |
| Tools | Dry-run records but never calls the network; idempotency test. |
| Bedrock layer | Mock client; budget guard tests; invalid-JSON handling; prompt delimiter test. |
| Store | In-memory SQLite; migration test; crash-recovery test. |
| Integration (slow, opt-in) | One real Decider call on CPU (marked `@slow`), one real Bedrock call (marked `@live`). CI skips both. |
| Backtest reproducibility | Golden test: fixed replay data + `FakeDecider` → fixed calibration numbers. |
| Pattern folder | Its own test suite, runnable without the rest of the repo. |

CI (GitHub Actions or local `make test`) runs on CPU with no model download and no AWS credentials.

---

## 15. Extension points (why the pattern is reusable)

- **Other decision domains:** swap `questions.py` and `policy.yaml`. The gate, bands, resolver, and handler are domain-agnostic (e.g., gate a `send_email` or `delete_record` tool on "does the user's request actually ask for this?").
- **Other agent frameworks:** use `ConfidenceGate` directly; only `handler.py` is Strands-specific.
- **Other decision backends:** implement `DeciderClient`.
- **Other sources:** implement an `Item` source (GitLab, Discourse, support inbox).

The `patterns/confidence_band_handler/README.md` should show one non-SlopGate example to prove this.

---

## 16. Open items the agent must verify early (day 1)

1. Strands Decider Python API for asking multiple questions about one state in a single call; confirm prefix reuse.
2. Exact `InterventionHandler` import path, `before_tool_call` signature, and action return types (`Proceed`, `Deny`, `Confirm`, `Guide`).
3. Whether direct (non-LLM) tool invocations pass through interventions.
4. How to pass per-invocation context to the handler.
5. `strands-decider serve` request/response format (only if using `HttpDecider`).
6. Which small Bedrock model is enabled in the user's account/region, and its price per token for the cost config.
7. CPU latency per question and per item on the user's machine, then adjust section 9 targets and state length.

Record each finding in `docs/VERIFIED.md` (one line each, with the command or source used).

---

## 17. Architecture summary in one paragraph

SlopGate is a single-process, CPU-local pipeline: ingest → compact state with code-extracted facts → Decider 2B typed questions (cached, cascaded) → pure confidence-band policy → most-restrictive action plan → either a scripted executor (routine) or a Bedrock-driven Strands agent (hard cases), with every tool call gated by a reusable `ConfidenceBandHandler` and every decision recorded as a receipt. Bedrock writes and reasons only when needed, within a budget guard. Nothing is closed without a human.
