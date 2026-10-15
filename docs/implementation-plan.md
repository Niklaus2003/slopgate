# SlopGate — Implementation Plan

**Audience:** the coding agent building SlopGate (and the human supervising it).
**Companions:** `problem-statement.md` (what and why) and `architecture.md` (how). This file is the **ordered build plan**, and it is also the **progress tracker**.

**Deadline:** Oct 23, 2026, 11:59 p.m. PT. Today is Oct 15. Plan for submission by **Oct 22** and use Oct 23 only as buffer.

---

## READ THIS FIRST — mandatory operating rules

1. **Phase 0 comes before any code.** You must read `problem-statement.md` and `architecture.md` **completely and carefully** (every section, including tables and code sketches), then write two documents proving you understood them and checked the plan. Details are in Phase 0. Do not skip or summarize lazily.
2. **Everything installs inside a virtual environment.** Never install packages globally, never use `--break-system-packages`, never `sudo pip`. Phase 1 gives exact commands. Every shell session that runs project code must have the venv activated (check with the verification commands in Phase 1).
3. **Secrets live only in `.env`.** Create `.env` from `.env.example`, make sure `.env` is in `.gitignore` **before the first commit**, never print key values, never paste them into logs, docs, tests, or commits.
4. **You update this file as you work.** When a step or phase is finished you must tick the checkbox, update the status table, and add an entry to the Phase Log (section at the bottom). See "How to mark progress."
5. **Do not invent APIs.** Strands Decider, the Strands Agents `InterventionHandler`, and Bedrock model IDs are new or account-specific. Verify by reading source/examples and running small experiments. Record findings in `docs/VERIFIED.md`.
6. **Stop and report to the human** at the checkpoints marked **🛑 CHECKPOINT** (after Phase 0, Phase 1, and Phase 8). Wait for confirmation before continuing.
7. **Dry-run by default.** Never write to a real third-party GitHub repo. Only the user's own sandbox repo may receive live writes, and only with `--live`.
8. **Never fake results.** Every number in the README/article must come from a script in the repo.
9. If something in this plan conflicts with what you observe in the real libraries, **trust the observation**, note the conflict in `docs/PLAN_REVIEW.md` (Phase 0) or the Phase Log (later), and tell the human.
10. **Phase completion reports for the human:** At the conclusion of every single phase, you must provide a detailed, clear breakdown report to the human explaining:
    - **What changes were made:** files created/modified, components, schemas, or tests added.
    - **What was done:** step-by-step summary of the actions taken.
    - **Why it was done:** the architectural, safety, or domain rationale behind those decisions.
    - **What its use is:** how this capability connects to the rest of the system and what it unlocks next.

---

## How to mark progress

**Status legend:** ⬜ Not started · 🟨 In progress · ✅ Done · ⛔ Blocked

**Rules:**
- Change a phase to 🟨 when you begin it.
- Tick a checkbox (`- [x]`) only when that item is actually done **and verified** (command run, test passing, file present).
- A phase becomes ✅ **only when every Exit Criteria checkbox is ticked and the Phase Log entry contains evidence** (test counts, measured timings, file paths, short command output summaries, never secrets).
- If blocked, set ⛔, write the blocker and what you need from the human in the Phase Log.
- Edit this file in place; do not create a separate tracker.

### Progress dashboard (keep this table current)

| Phase | Title | Target date | Status |
|---|---|---|---|
| 0 | Read, understand, and verify the plan | Oct 15 | ✅ |
| 1 | Environment, `.env`, repo scaffold, smoke tests | Oct 15–16 | ⬜ |
| 2 | Core types, config, storage, pure policy logic | Oct 16 | ⬜ |
| 3 | Ingestion, replay data, facts, state builder | Oct 16–17 | ⬜ |
| 4 | Decider integration, questions, cascade, caching | Oct 17 | ⬜ |
| 5 | Agent tools, `ConfidenceBandHandler`, executor | Oct 18 | ⬜ |
| 6 | Bedrock layer, escalation, LLM agent, review flow | Oct 18–19 | ⬜ |
| 7 | End-to-end worker, CLI, receipts | Oct 19 | ⬜ |
| 8 | Backtest, baseline, calibration, threshold tuning | Oct 20 | ⬜ |
| 9 | Reusable pattern package | Oct 21 | ⬜ |
| 10 | Next.js Interactive Dashboard, Demo Showcase, & API | Oct 21 | ⬜ |
| 11 | Docs, article, video script, submission checklist | Oct 22 | ⬜ |

---

## Technology connection map (use this to reason about how things fit)

| Technology | Role | Connects to | How it connects | First verified in |
|---|---|---|---|---|
| GitHub REST API | Source of issues/PRs (read); sandbox writes (live only) | Ingestor → SQLite | HTTPS + optional token; ETag caching; replay JSON for tests | Phase 1, 3 |
| SQLite | Queue, cache, receipts, ground truth | Everything | `store/db.py` repository functions, WAL mode | Phase 2 |
| Code-based fact extractors | Deterministic evidence | State builder | Pure functions over item + repo index | Phase 3 |
| **Strands Decider 2B** (local, CPU) | Typed decisions with calibrated confidence | Cascade → policy layer | In-process `StrandsDeciderModel` (or `serve` HTTP), loaded once | Phase 1, 4 |
| Policy layer (`bands`, `gate`, `resolver`) | Turns (answer, confidence) into Proceed/Confirm/Guide/Deny | Handler, executor | Pure Python, config from `policy.yaml` | Phase 2 |
| **Strands Agents SDK** | Tool-calling agent runtime + `InterventionHandler` | Tools, handler, Bedrock model | `ConfidenceBandHandler.before_tool_call` wraps the gate | Phase 1, 5 |
| **Amazon Bedrock** | Reply drafting, hard-case reasoning, LLM agent brain, baseline | Escalation layer, Strands agent | boto3 / Strands Bedrock model provider; model ID from `.env` | Phase 1, 6 |
| **Next.js Dashboard & Local API** | Interactive UI, live triage simulator, review inbox, calibration charts | SQLite / Local API (`slopgate serve`) | REST / JSON API (`GET /api/items`, `POST /api/triage`, `POST /api/approvals`); dark-mode UI | Phase 10 |
| `.env` | Keys/config | All network clients | `python-dotenv` at startup | Phase 1 |

**End-to-end in one sentence:** GitHub items → SQLite queue → compact state (text + code-extracted facts) → Decider 2B answers typed questions on CPU → the policy layer turns confidence into an action → routine actions run through a scripted executor, hard ones go to a Bedrock-driven Strands agent, and every tool call passes through `ConfidenceBandHandler` → receipts and calibration report are generated from SQLite.

---

# PHASE 0 — Read, understand, and verify the plan

**Goal:** prove you understand the project end to end, and that this plan actually works, **before writing code**.

### Steps

1. Read `problem-statement.md` in full. Read `architecture.md` in full. Then read this plan in full.
2. Create the folder `docs/` and write **`docs/UNDERSTANDING.md`** containing, in your own words:
   - **What we are building and for whom** (the problem, the audience, why a confidence-gated local decision model is the right tool).
   - **The end-to-end data flow**, step by step, from a GitHub issue to a labeled/commented/escalated outcome.
   - **How each technology connects to the others** (expand the connection map above: what data crosses each boundary, in what format, and which module owns it).
   - **What Decider 2B does and does not do**, its question types, how confidence is defined, its known limits, and what that means for our design (no `score` questions, cascade, thresholds, wording sensitivity).
   - **How the reusable pattern is separated from the app** (framework-free `ConfidenceGate` + thin Strands adapter) and why.
   - **The safety model** (never auto-close, newcomers protected, untrusted text, dry-run).
   - **How hackathon requirements map to deliverables** (article, public OSI-licensed repo with labeled reusable pattern, <3 min video, tags `#strands-decider-2b` and `#policy`, originality, deadline).
   - **What you would explain to a new engineer in 5 minutes** (a short narrative, max ~250 words).
3. Write **`docs/PLAN_REVIEW.md`** verifying this plan against both documents:
   - List every place where `implementation-plan.md`, `architecture.md`, and `problem-statement.md` **disagree or are ambiguous**.
   - List **missing steps, hidden dependencies, and ordering problems** (e.g., something needed in an early phase that a later phase creates).
   - List **risks to the Oct 22 target** and what you would cut first (use the P0/P1/P2 priorities in `problem-statement.md` §12).
   - List every **`VERIFY` item** from `architecture.md` §16 and say exactly how and in which phase you will verify each.
   - Propose concrete **plan changes** (if any) as a short diff-style list. Do not silently change the plan; propose and wait.
4. Write at the end of `docs/PLAN_REVIEW.md` a section **"Questions for the human"** covering at minimum: CPU model/cores/RAM; AWS region and whether Bedrock model access is enabled (and for which small model); which public repo to backtest on (offer 2–3 candidates that meet `problem-statement.md` §13 criteria); sandbox GitHub repo for the live demo; MIT vs Apache-2.0; OS (Windows/macOS/Linux) so venv commands are right; Python version installed.
5. Tick the Phase 0 boxes, update the dashboard, and write the Phase Log entry.

### Exit criteria
- [x] Read `problem-statement.md` completely
- [x] Read `architecture.md` completely
- [x] `docs/UNDERSTANDING.md` written with all required sections
- [x] `docs/PLAN_REVIEW.md` written (disagreements, gaps, risks, VERIFY mapping, proposed changes, questions)
- [x] Dashboard updated and Phase Log entry added

### 🛑 CHECKPOINT 0
Stop. Present a short summary of `UNDERSTANDING.md` and the key findings of `PLAN_REVIEW.md` to the human, ask the questions, and **wait for approval** before Phase 1.

---

# PHASE 1 — Environment, `.env`, repo scaffold, smoke tests

**Goal:** a clean venv with everything installed inside it, a safe `.env`, a project skeleton, and **proof that each external technology works on this machine** (Decider on CPU, Strands SDK, Bedrock, GitHub API).

### 1A. Create the repo and virtual environment

Run from the project root (`slopgate/`). Use the human's OS.

**macOS / Linux**
```bash
python3 --version                  # confirm 3.10+ (check strands-decider's required version on PyPI)
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
which python                       # must point inside .../slopgate/.venv/
```

**Windows (PowerShell)**
```powershell
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1       # if blocked: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
python -m pip install --upgrade pip
(Get-Command python).Source        # must point inside ...\slopgate\.venv\
```

**Rules**
- Confirm the venv is active before **every** `pip install` and every run. The prompt should show `(.venv)`.
- Install only with `python -m pip install ...` (guarantees the venv's pip).
- Pin and freeze: after installs, `python -m pip freeze > requirements.lock.txt`. Maintain a human-readable `requirements.txt` for direct dependencies.
- Add `.venv/` to `.gitignore`.

### 1B. Install dependencies (inside the venv)

Start with the CPU-friendly PyTorch if the default would pull a large CUDA build (Windows/Linux). **VERIFY** this is needed and compatible with `strands-decider`'s requirements before doing it:
```bash
# optional, only if you want to avoid a multi-GB CUDA wheel on a CPU-only machine
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
```
Then:
```bash
python -m pip install strands-decider strands-agents boto3 python-dotenv pyyaml pydantic httpx \
                      scikit-learn rank-bm25 pytest pytest-cov ruff
```
- If any package name or version conflicts, resolve it and record the resolution in `docs/VERIFIED.md`.
- Optional later: `mypy`. Do not install anything not used.

### 1C. Create `.env` for keys and settings

1. Create **`.env.example`** (committed, no real values):
   ```
   # ---- AWS / Bedrock ----
   AWS_REGION=us-east-1
   BEDROCK_MODEL_ID=amazon.nova-micro-v1:0
   # Option A: standard AWS credentials
   AWS_ACCESS_KEY_ID=
   AWS_SECRET_ACCESS_KEY=
   AWS_SESSION_TOKEN=
   # Option B: Bedrock API key (if you use one)
   AWS_BEARER_TOKEN_BEDROCK=

   # ---- GitHub ----
   GITHUB_TOKEN=            # optional for reading public repos (raises rate limits)
   GITHUB_WRITE_TOKEN=      # ONLY for your own sandbox demo repo; leave empty otherwise
   GITHUB_SANDBOX_REPO=     # owner/name of your own demo repo

   # ---- SlopGate behavior ----
   SLOPGATE_DRY_RUN=1
   SLOPGATE_MAX_BEDROCK_CALLS=50
   SLOPGATE_MAX_OUTPUT_TOKENS=150
   SLOPGATE_DECIDER_THREADS=4
   SLOPGATE_DECIDER_MODEL=StrandsAgents/strands-decider-2B-hobson-v21
   SLOPGATE_DECIDER_DEVICE=cpu
   ```
2. Copy it: `cp .env.example .env` (Windows: `copy .env.example .env`).
3. **Add `.env`, `.venv/`, `*.db`, `data/cache/`, `__pycache__/` to `.gitignore` before the first `git commit`.** Verify with `git status` that `.env` is not tracked.
4. Tell the human exactly which values to fill in and where to get them:
   - **AWS (free-tier-friendly):** create a **new** AWS account on the **Free plan** if possible (accounts created before July 15, 2025 are on the legacy program). Free-plan credits last 6 months or until used, then the account closes; the paid plan keeps billing after credits end. Create an **AWS Budgets** alert regardless. In the console, enable access to a small model in Bedrock for the chosen region, then either create an IAM user/role with `bedrock:InvokeModel*` permissions (least privilege) or generate a Bedrock API key (set an expiry). Put the region, model ID, and credentials in `.env`.
   - **GitHub:** a fine-grained personal access token with **read-only public repo access** is enough for ingestion. A separate write-scoped token is for the **sandbox repo only**.
5. Load `.env` with `python-dotenv` at startup in `config.py`. Never log values.
6. Implement **`slopgate doctor`** (first CLI command): prints which variables are **set/unset** (never the values), which Python is running (must be inside `.venv`), library versions, and detected CPU cores/RAM.

### 1D. Repo scaffold
- Create the directory layout from `architecture.md` §4 (empty modules with docstrings are fine), `pyproject.toml`, `README.md` stub, `LICENSE` (per the human's choice), `Makefile` or simple scripts (`make test`, `make lint`).
- `git init`, first commit **after** `.gitignore` is correct. Keep the GitHub repo **private** until Phase 11.
- Create `docs/VERIFIED.md` (one line per verified fact: what, how, date).

### 1E. Smoke tests (prove each technology works; record results)

1. **Decider on CPU (CLI):**
   ```bash
   strands-decider ask StrandsAgents/strands-decider-2B-hobson-v21 --device cpu \
     --state "Help! My payouts have been failing for 3 days!" \
     --choice "Which team should handle this?=billing,sales,retail" \
     --noul "Does this convey urgency?"
   ```
   First run downloads weights from the Hugging Face Hub (needs internet and disk space). Time a second run.
2. **Decider in Python (load once, ask many):** write `scripts/smoke_decider.py` that loads the model once, asks 5 questions about one ~400-token realistic issue, prints per-question latency, and shows whether asking several questions about the same state is cheaper than separate calls. Record the machine spec and the numbers. **VERIFY** the Python API for multiple questions per state.
3. **Strands Agents + Bedrock:** `scripts/smoke_strands.py` creates a minimal Strands agent with a Bedrock model and one trivial tool, and gets one response. Also a raw `boto3` `bedrock-runtime` Converse call to confirm credentials, region, and model ID. **VERIFY** the exact model provider class/import.
4. **Intervention example:** clone `github.com/strands-labs/strands-decider` into a git-ignored `_refs/` folder; read `examples/strands/`; run it if feasible. Write in `docs/VERIFIED.md`: the `InterventionHandler` import path, `before_tool_call` signature, return types (`Proceed`/`Deny`/`Confirm`/`Guide`), how per-invocation context can be passed, and whether direct tool invocations pass through interventions.
5. **GitHub:** fetch 5 issues from the chosen public repo with and without a token; note rate-limit headers.

### Exit criteria
- [ ] `.venv` created; `which python`/`Get-Command python` proves it is inside the project
- [ ] All dependencies installed inside the venv; `requirements.txt` and `requirements.lock.txt` written
- [ ] `.env.example` committed; `.env` created by the human, **git-ignored and verified untracked**
- [ ] `slopgate doctor` runs and reports variables set/unset without printing secrets
- [ ] Repo scaffold, `LICENSE`, `.gitignore`, first commit done (repo private)
- [ ] Decider CLI smoke test passes on CPU; latency recorded
- [ ] Python load-once smoke test passes; per-question and multi-question timings recorded
- [ ] Strands + Bedrock smoke test passes (one real response)
- [ ] Intervention example read; API facts recorded in `docs/VERIFIED.md`
- [ ] GitHub smoke test passes
- [ ] `docs/VERIFIED.md` covers all seven `VERIFY` items from `architecture.md` §16 (or states what is still unknown)

### 🛑 CHECKPOINT 1
Report to the human: machine spec, seconds per question and per item estimate, which `VERIFY` items are resolved, any plan changes needed (e.g., shrink state if > ~10 s/item). **Wait for confirmation.**

---

# PHASE 2 — Core types, config, storage, pure policy logic

**Goal:** the model-free, network-free backbone, fully unit-tested.

### Steps
1. `models.py`: dataclasses/enums from `architecture.md` §5.1.
2. `config.py`: load `.env` and `policy.yaml`; validate with pydantic; **unknown keys are errors**. Provide `policy.example.yaml` (from `architecture.md` §8.1).
3. `store/schema.sql` and `store/db.py`: tables from `architecture.md` §5.3, WAL mode, transactional helpers, crash-recovery (reset stale `processing`).
4. `policy/bands.py`: choice by normalized confidence, noul by `P(true)` thresholds (never a bare bool).
5. `policy/gate.py` (`ConfidenceGate`): proposed tool call + decisions → `GateVerdict`. **Hard rules in code:** `close_item` is never Proceed; `security_report` is at least Confirm; unlisted tools are Confirm.
6. `policy/resolver.py`: most-restrictive-wins, severity `DENY > CONFIRM > GUIDE > PROCEED`.
7. `decider/client.py`: define the `DeciderClient` protocol and a **`FakeDecider`** (scripted, no model).
8. Tests: table-driven tests for bands, gate (every hard rule at every confidence), resolver, DB (in-memory), config validation.

### Exit criteria
- [ ] Types, config, schema, DB helpers implemented
- [ ] `bands`, `gate`, `resolver` implemented with hard rules in code
- [ ] `FakeDecider` implemented
- [ ] Unit tests pass (`pytest -q`), including the "`close_item` never Proceed" test
- [ ] No test downloads a model or uses the network or credentials

---

# PHASE 3 — Ingestion, replay data, facts, state builder

**Goal:** turn real issues/PRs into compact, fact-rich state strings.

### Steps
1. `ingest/github.py`: REST client, pagination, ETag cache, rate-limit backoff, token optional.
2. `ingest/replay.py` and `slopgate ingest --save data/samples/<name>.json` to snapshot data once, so later work is offline and reproducible.
3. `state/repo_index.py`: file tree + symbol index, cached with TTL.
4. `state/facts.py`: one pure function per fact (cited paths found, code block, repro heading, template sections, linked issues, CI status, contributing excerpt). `state/similarity.py`: TF-IDF/BM25 duplicate candidates.
5. `state/builder.py`: exact format from `problem-statement.md` §6.1; enforce token cap (truncate body, then files, never facts); compute `state_hash` including a `schema_version`. Exclude author-history unless the policy flag is on.
6. Unit tests on fixture items; verify truncation order and hash stability.

### Exit criteria
- [ ] Live ingestion works for a public repo; snapshot saved to `data/samples/`
- [ ] Replay ingestion works offline
- [ ] All fact extractors implemented with unit tests
- [ ] State builder meets the token cap on 100% of sampled items; truncation logged
- [ ] Hash is stable across runs; changes when `schema_version` bumps
- [ ] Author-history facts absent by default (tested)

---

# PHASE 4 — Decider integration, questions, cascade, caching

**Goal:** real Decider decisions on real states, cached, measured.

### Steps
1. Implement `InProcessDecider` using the API verified in Phase 1 (load once; batch follow-ups so the state is read once). Optionally `HttpDecider` for `strands-decider serve`.
2. `decider/questions.py`: Q1 (issue and PR variants) and N1–N5 from `problem-statement.md` §7. **Only `choice` and `noul`.**
3. `decider/cascade.py`: Q1 → conditional follow-ups in one batched call → early exit.
4. Caching in SQLite keyed by `(state_hash, question_id, question_text_hash, model_id)`.
5. **Wording experiment:** for Q1 and N1, test 2–3 wording variants on ~30 items; keep the variant that behaves best; record results in `docs/VERIFIED.md`.
6. Measure per-item time on this CPU; if > ~10 s, apply the state-shrink rule.
7. Integration test marked `@slow` (real model, 3 items). CI/unit tests keep using `FakeDecider`.

### Exit criteria
- [ ] `InProcessDecider` works; model loaded once per process
- [ ] Questions registered; cascade with early exit working
- [ ] Cache hit verified (second run of the same items makes no model calls)
- [ ] Wording experiment recorded
- [ ] Per-item latency measured and recorded (p50/p95)
- [ ] `@slow` integration test passes locally

---

# PHASE 5 — Agent tools, `ConfidenceBandHandler`, executor

**Goal:** actions flow through the gate, safely and idempotently, in dry-run.

### Steps
1. `agent/tools.py`: `apply_label`, `post_comment`, `request_info_comment`, `flag_for_maintainer`, `close_item`. Every write checks dry-run; every tool computes an idempotency key and skips duplicates.
2. `agent/handler.py`: `ConfidenceBandHandler` as a **thin adapter over `ConfidenceGate`**, using the verified `InterventionHandler` API. Bind per-item context the way you verified in Phase 1.
3. `agent/executor.py`: `ScriptedExecutor` for routine plans. If direct tool calls do not pass through interventions (per Phase 1), call `gate.evaluate` explicitly before each tool; document this in `docs/VERIFIED.md`.
4. Start the `patterns/confidence_band_handler/` folder (copy of gate + bands + handler, no imports from `src/slopgate/`).
5. Tests: fake agent/event → each verdict maps to the correct return type; dry-run never touches the network; idempotency.

### Exit criteria
- [ ] Tools implemented, dry-run safe, idempotent
- [ ] Handler returns Proceed/Confirm/Guide/Deny correctly (tests)
- [ ] Executor runs a full routine plan in dry-run
- [ ] `close_item` provably cannot execute without approval (test)
- [ ] Pattern folder scaffolded with no imports from the app

---

# PHASE 6 — Bedrock layer, escalation, LLM agent, review flow

**Goal:** Bedrock used only where needed, within a budget, safely.

### Steps
1. `bedrock/client.py`: invoke wrapper (Converse or the Strands provider, per Phase 1), retries with jitter, region/model from `.env`.
2. `bedrock/budget.py`: call/token caps per run and per day; degrade gracefully (template reply or flag for maintainer).
3. `bedrock/prompts.py` and `escalate.py`: `draft_reply` (≤ ~120 words; kind, specific, no AI-authorship accusations) and `reason_on_ambiguous` (strict JSON; invalid JSON means failure → flag). **Wrap untrusted text in explicit delimiters; these two calls have no tools.**
4. `agent/llm_agent.py`: Bedrock-driven Strands agent with the tools and `ConfidenceBandHandler`, run **only** on escalated items.
5. `slopgate review`: list/approve/reject `pending_approvals`; `close_item` executes only via approval.
6. Tests with a mocked Bedrock client (budget exhaustion, invalid JSON, prompt delimiters); one `@live` test for a real call.

### Exit criteria
- [ ] Draft and reasoning calls work against real Bedrock (`@live`)
- [ ] Budget guard stops calls at the cap and degrades correctly (test)
- [ ] Prompt-injection test: hostile issue text does not change tool behavior
- [ ] LLM agent runs only on escalated items; every tool call passes the handler
- [ ] Review flow approves/rejects; close only via approval
- [ ] Token usage and estimated cost recorded in `escalations`

---

# PHASE 7 — End-to-end worker, CLI, receipts

**Goal:** `slopgate run` processes a queue end to end.

### Steps
1. Worker loop (`architecture.md` §3, §7): pop, state, cascade, plan, execute or escalate, receipt, status; graceful SIGINT; stale-processing recovery.
2. `cli.py`: `doctor | ingest | run | review | backtest | report | demo`.
3. `report/receipts.py`: JSON + Markdown receipts built from the tables.
4. Structured logging and a run summary (items, cache hits, escalations, tokens/cost, p50/p95).
5. End-to-end test with `FakeDecider` + mocked Bedrock; one manual end-to-end run on real data in dry-run.

### Exit criteria
- [ ] `slopgate run` drains a queue of ≥ 20 real replayed items end to end
- [ ] Receipt exists for every item and matches the actions taken
- [ ] Crash/restart recovery verified (kill mid-run, rerun, no duplicate actions)
- [ ] Run summary prints accurate counts and timings
- [ ] Full unit test suite green

---

# PHASE 8 — Backtest, baseline, calibration, threshold tuning

**Goal:** the evidence for the article: calibration, safety, speed, cost.

### Steps
1. Choose the backtest repo (human-approved). Snapshot 150–200 closed items to `data/samples/`.
2. Define the **proxy label** mapping (maintainer outcomes → our categories). Document its limits.
3. **Gold labels:** generate `data/gold/to_label.csv` with ~60 items (id, title, body excerpt). **The human labels these**; do not label them yourself, since honest ground truth matters. Load them into `ground_truth` with `source='gold'`.
4. `backtest/runner.py`: replay → state → cascade → plan, **never writing actions**. Store decisions.
5. `backtest/baseline.py`: the same items through a small Bedrock model on every item (capped sample, within the budget guard).
6. `report/calibration.py`: accuracy by confidence band, coverage, escalation rate, **false-reject rate on accepted items**, p50/p95 seconds/item, Bedrock tokens/cost vs baseline, wording-variant results, machine spec header. Output `reports/backtest.md` (and optionally HTML).
7. Tune thresholds in `policy.yaml` using the results; record before/after. Do not tune on the gold subset alone (avoid overfitting; keep a held-out slice).
8. Golden test: fixed replay data + `FakeDecider` → fixed report numbers.

### Exit criteria
- [ ] Backtest runs from cached data reproducibly
- [ ] Gold labels received from the human and loaded
- [ ] Baseline run completed within budget
- [ ] Calibration report generated with all metrics and machine spec
- [ ] Thresholds tuned with a held-out check; before/after recorded
- [ ] Failure cases documented ("where it was wrong and what the confidence said")

### 🛑 CHECKPOINT 8
Present the headline numbers and the threshold decisions to the human. **Wait for confirmation** before polishing and publishing claims.

---

# PHASE 9 — Reusable pattern package

**Goal:** the hackathon's required reusable asset, clean and independent.

### Steps
1. Finalize `patterns/confidence_band_handler/`: `handler.py`, `bands.py`, `policy.example.yaml`, `example_agent.py`, `tests/`, `README.md`. **No imports from `src/slopgate/`.**
2. README "recipe card": the typed question(s) and option set, the wiring snippet, threshold guidance, low-confidence behavior, and a 5-minute quickstart.
3. Add one **non-SlopGate example** (e.g., gating a `send_email` or `delete_record` tool on "does the user's request actually ask for this?") to prove reusability.
4. The pattern's tests must pass in a fresh venv with only the pattern's own requirements.
5. Label it prominently in the root README: **"Reusable Strands Decider 2B decision pattern."**
6. Optional: `patterns/grounding_check/`.

### Exit criteria
- [ ] Pattern folder is self-contained; tests pass in a fresh venv
- [ ] README recipe card complete, with non-SlopGate example
- [ ] Root README labels and links the pattern
- [ ] Pattern uses the verified `InterventionHandler` API

---

# PHASE 10 — Next.js Interactive Dashboard, Demo Showcase, & API

**Goal:** a stunning, modern Next.js web application and local API (`slopgate serve`) to test SlopGate interactively, showcase its triage decisions to users, review pending approvals, and provide compelling visuals for the submission video and article.

### Steps
1. **Lightweight Local API Server (`src/slopgate/api/server.py`):**
   - Command: `slopgate serve [--port 8000]`
   - Endpoints:
     - `GET /api/items`: list ingested/queued/decided items with filtering (by status, band, repo).
     - `GET /api/items/{id}/receipt`: fetch structured JSON and rendered Markdown decision receipt.
     - `POST /api/triage`: on-demand triage endpoint (accepts title, body, PR diff facts; executes state builder, Decider cascade, gate, and optional Bedrock draft/reasoning in real time).
     - `POST /api/approvals/{id}/action`: approve or reject pending actions (executing stored plan in dry-run or live mode).
     - `GET /api/stats/calibration`: aggregate calibration metrics (accuracy per band, coverage, latency percentiles, Bedrock token costs vs baseline).
     - `GET /api/demo/fixtures`: return pre-seeded synthetic demo items for one-click UI testing.
2. **Next.js Web Application (`web/`):**
   - Built with Next.js (App Router), Vanilla CSS / CSS Modules with rich design tokens, dark mode, glassmorphism, and responsive layouts.
   - **Page 1: Live Triage Simulator & Demo Playground:**
     - Interactive form allowing the user to paste any GitHub issue or PR text, or click one-click preset buttons for 6 seeded demo scenarios (clean bug, missing repro, duplicate, low effort, PR needing explanation, ambiguous security report).
     - Live visualization of deterministic fact extraction (symbols verified against repo index, template compliance, code blocks, BM25 similarity).
     - Visual Decider 2B inference readout: question-by-question cascade, option probability distribution bars, and normalized confidence gauge.
     - Confidence-band badges (`HIGH` in green, `MEDIUM` in amber, `LOW/UNCERTAIN` in purple).
     - Action routing verdict badge (`PROCEED`, `CONFIRM`, `GUIDE`, `DENY`).
     - Real-time display of Amazon Bedrock draft or ambiguity reasoning when triggered.
   - **Page 2: Maintainer Triage Inbox & Review Queue:**
     - Filterable list of all items in SQLite (`pending_approval`, `executed`, `flagged`).
     - Card view displaying item title, type, author, state hash, and confidence band.
     - One-click maintainer actions: **Approve Plan** or **Reject / Dismiss Plan**.
     - Full slide-out drawer showing the complete Markdown Decision Receipt and evidence trail.
   - **Page 3: Calibration & Safety Analytics:**
     - Interactive visual charts of backtest results:
       - Accuracy across confidence bands (demonstrating calibrated safety).
       - Escalation rate and Bedrock cost savings compared to a 100% Bedrock baseline.
       - False-reject rate on legitimate community items (target: 0.0%).
       - p50/p95 latency breakdown (Decider CPU forward pass vs Bedrock network call).
3. **Demo Fixtures & Video Rehearsal:**
   - Seed `demo/` fixtures with 6–8 curated test items.
   - Verify `slopgate demo` (CLI) and the Next.js UI both demonstrate the core story cleanly:
     - (1) High-confidence bug auto-labeled `triaged` (Proceed).
     - (2) Low-effort item receives soft label `needs-more-detail` + empathetic Bedrock draft (Proceed-soft, no close).
     - (3) Ambiguous item escalates to Bedrock reasoning (Guide -> Confirm).
     - (4) Destructive close attempt is strictly Denied without maintainer sign-off.
   - Record UI interactions for the `< 3 min` submission video.

### Exit criteria
- [ ] `slopgate serve` starts local API server on `http://localhost:8000` with JSON endpoints
- [ ] Next.js frontend builds and runs cleanly (`npm run dev`) on `http://localhost:3000`
- [ ] Triage Simulator processes on-demand input and displays facts, Decider confidence, and Bedrock output
- [ ] Maintainer Review Inbox allows viewing receipts and approving/rejecting pending items
- [ ] Calibration Analytics page visualizes backtest metrics and cost savings
- [ ] UI is fully responsive, dark-mode themed, with rich aesthetics and micro-animations
- [ ] Demo scenarios rehearsed and recorded for `VIDEO_SCRIPT.md`

---

# PHASE 11 — Docs, article, video script, submission checklist

**Goal:** everything required to qualify and score well.

### Steps
1. `README.md`: problem, architecture diagram, quickstart (including the venv + `.env` steps), configuration, the pattern, honest limitations, measured results (copied from scripts' output).
2. `ARTICLE.md` (Builder Center draft): problem, the decision handed to Decider and why, confidence-band design, what Bedrock does, backtest results on ordinary CPU hardware, failures and lessons, how to reuse the pattern. Tags: `#strands-decider-2b` `#policy`.
3. `VIDEO_SCRIPT.md` (≤ 2:45): problem → queue → auto-handled item with receipt → ambiguous item escalated and confirmed → reusable handler config → calibration chart → close. No third-party logos or copyrighted music; label sped-up parts.
4. Security pass: grep for secrets (`AKIA`, `aws_secret`, tokens), confirm `.env` was never committed (`git log --all -- .env`), rotate any key that ever leaked.
5. License check (OSI), `LICENSE` present, third-party license notes for data samples.
6. Make the repo **public**, verify the clone-and-run quickstart in a fresh directory and a fresh venv.
7. Human tasks (agent prepares, human does): publish the article on AWS Builder Center, upload the video (YouTube/Vimeo/etc.), add both tags, submit.

### Exit criteria
- [ ] README complete; quickstart verified from scratch in a fresh venv
- [ ] All README numbers traceable to scripts
- [ ] `ARTICLE.md` and `VIDEO_SCRIPT.md` drafted
- [ ] Secrets scan clean; `.env` never committed
- [ ] OSI license present; repo public
- [ ] Human has: article published with tags, video public (< 3 min), repo link, submitted before Oct 23 11:59 p.m. PT

---

## Final verification matrix (maps acceptance criteria to phases)

| Acceptance criterion (`problem-statement.md` §16) | Verified in |
|---|---|
| Runs end to end on CPU-only machine in dry-run, no paid services | Phases 1, 7, 10 |
| Decider used for real decisions (Q1 + ≥2 noul), loaded once, latency recorded | Phase 4 |
| Strands agent routes tool calls through `ConfidenceBandHandler` | Phases 5, 6 |
| `close_item` never runs without approval (test) | Phases 2, 5, 6 |
| Bedrock only for drafts/escalations, within budget guard, tokens logged | Phase 6 |
| Receipt for every item | Phase 7 |
| Backtest reproduces calibration report with machine specs | Phase 8 |
| Reusable pattern folder self-contained, tested, labeled | Phase 9 |
| OSI license, README, no secrets | Phase 11 |
| All reported numbers come from scripts | Phases 8, 11 |

---

## If you fall behind (cut order)

Cut in this order, and record each cut in the Phase Log: (1) optional HTML report and second pattern, (2) wording-variant breadth, (3) `HttpDecider`, (4) LLM-agent path (keep `reason_on_ambiguous` + review flow), (5) backtest size (never below ~100 items). **Never cut:** the reusable pattern, the backtest/calibration report, the safety rules, the README, the article, or the video.

---

## Phase Log (append an entry when a phase is finished or blocked)

**Template**
```
### Phase N — <title> — <✅ Done | ⛔ Blocked> — <date>
- What was done:
- Evidence (commands run, test counts, file paths, measured numbers; NO secrets):
- Deviations from the plan and why:
- Open issues / next steps:
```

### Phase 0 — Read, understand, and verify the plan — ✅ Done — 2026-10-15
- What was done: Read `problem-statement.md`, `architecture.md`, and `implementation-plan.md` in full. Created `docs/UNDERSTANDING.md` with complete architecture, data flow, safety model, technology connection map, and engineer narrative. Created `docs/PLAN_REVIEW.md` analyzing document discrepancies, hidden dependencies (Windows, repo tree snapshots for offline replay, gold label timing), risk mitigations, verification roadmap for all 7 unverified items, and questions for the user.
- Evidence: `docs/UNDERSTANDING.md` (207 lines, 8 sections), `docs/PLAN_REVIEW.md` (124 lines, 6 sections).
- Deviations from the plan and why: Recommended generating `data/gold/to_label.csv` and offline repo file tree snapshot early in Phase 3 to avoid blocking on Phase 8 human labeling and to guarantee offline reproducibility.
- Open issues / next steps: Present Checkpoint 0 report and questions to user; await user input on CPU, AWS/Bedrock settings, repo choice, and license before starting Phase 1.
