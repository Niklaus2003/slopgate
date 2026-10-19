# FLOW: SlopGate System Execution Map

> **Trace from Entry Point to Execution Output.**
> Answers: *"Walk me through one request from entry to response."*
> Follows: *Defend What You Ship v2 (Section 01, Habit 4)*

---

## 1. End-to-End Execution Flow Diagram

```text
[Input Sources]
  GitHub Webhook / REST Poller / Offline Replay JSON
                           │
                           ▼
[Step 1: Ingestion & Deduplication]
  slopgate.ingest.github / slopgate.ingest.replay
  - Validates payload structure
  - Inserts raw item into SQLite queue (`items` table, status='QUEUED')
                           │
                           ▼
[Step 2: State Construction (Deterministic)]
  slopgate.state.builder.build_state(item)
  - Extracts code facts (diff length, test touched, reproduction provided)
  - Truncates body & diff to <= 450 tokens
  - Produces typed `State` object
                           │
                           ▼
[Step 3: In-Process Decider Inference (CPU)]
  slopgate.decider.client.evaluate(state, questions)
  - Evaluates Q1 (Choice question: TRIAGE_ACTION)
  - Evaluates N1-N5 (Noul questions: factual verification)
  - Returns `DeciderResult` with normalized probabilities & calibrated confidence
                           │
                           ▼
[Step 4: Policy & Safety Gating]
  slopgate.policy.gate.ConfidenceGate.evaluate(result)
  - Maps calibrated confidence to Bands:
      * >= 0.85 ──► HIGH
      * 0.60 - 0.85 ──► MEDIUM
      * < 0.60 ──► LOW
  - INVARIANT CHECK: If action is `close_item` ──► FORCE CONFIRM
  - Resolves verdict via `ActionResolver`:
      * HIGH ──► Proceed (routine action plan)
      * MEDIUM ──► Confirm (queued for human approval)
      * LOW / Ambiguous ──► Guide (escalates to Bedrock)
      * Violation ──► Deny (rejected with explanation)
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
[Step 5A: Routine Execution]    [Step 5B: Bedrock Escalation]
  slopgate.agent.executor         slopgate.bedrock.client
  - If DRY_RUN=1:                 - Checks 50-call budget guard
    Simulate & record planned     - Invokes Nova Micro (`converse`)
    labels/comments.              - Synthesizes empathetic guidance
  - If DRY_RUN=0 & sandbox:       - Updates `ActionPlan` with draft
    Mutate sandbox via API.                       │
             │                                    │
             └─────────────┬──────────────────────┘
                           ▼
[Step 6: Receipt & Audit Generation]
  slopgate.store.db / slopgate.report
  - Writes `receipts` row into SQLite (audit log)
  - Updates item status to 'PROCESSED' or 'PENDING_CONFIRMATION'
  - Emits structured JSON and Markdown receipt
```

---

## 2. Function Call Chain

```text
slopgate.cli.main()
 └── cli.triage()
      └── ingest.github.fetch_item(repo, number)
           └── store.db.save_item(item)
                └── state.builder.build_state(item)
                     └── decider.client.DeciderClient.evaluate(state, questions)
                          │    └── [CPU Model Forward Pass: Qwen3.5-2B torso]
                          │
                          └── policy.gate.ConfidenceGate.evaluate(decider_result)
                               ├── policy.bands.compute_band(confidence)
                               ├── policy.resolver.resolve_verdict(bands, actions)
                               │
                               ├── [If Verdict == Guide]:
                               │    └── bedrock.client.BedrockClient.reason_on_ambiguous(state)
                               │
                               └── agent.executor.execute_plan(plan, dry_run=True)
                                    └── store.db.record_receipt(receipt)
```

---

## 3. Trust Boundaries & Data Transitions

| Boundary | Incoming Data | Validation / Sanitization | Outgoing Action |
| :--- | :--- | :--- | :--- |
| **External Untrusted ──► Ingestion** | Raw GitHub JSON / user webhook | Validated via Pydantic `Item` schema; fields stripped of malformed control chars. | Normalized `Item` in SQLite. |
| **Ingestion ──► State Builder** | Normalized `Item` | Truncated to strict <= 450 tokens; code facts extracted deterministically. | Clean `State` object. |
| **State Builder ──► Local Decider** | Clean `State` | Bound to typed `Question` schemas (`choice`, `noul`). | Raw logits & softmax probabilities. |
| **Decider ──► Confidence Gate** | `DeciderResult` | Enforces zero-auto-close invariant; maps continuous float to discrete Band. | `GateVerdict` (`Proceed`, `Confirm`, `Guide`, `Deny`). |
| **Gate ──► Amazon Bedrock** | Ambiguous item state | Prompt injection defenses: prompt wrapped in `<issue_context>` tags; hard token cap. | Empathetic guidance text. |
| **Execution ──► GitHub API** | `ActionPlan` | Mutating actions blocked unless `SLOPGATE_DRY_RUN=0` AND repository is sandbox. | Live label or comment on sandbox. |
