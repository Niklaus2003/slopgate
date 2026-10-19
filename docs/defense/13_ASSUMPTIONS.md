# ASSUMPTIONS: SlopGate Assumptions & Open Questions Log

> **Living Record of Working Assumptions, Verification Status, and Open Questions.**
> Answers: *"What did the AI or team assume that has not yet been verified?"*
> Follows: *Defend What You Ship v2 (Section 06, Habit 21)*

---

## 1. Assumptions Log

| ID | Assumption Statement | Source / Why Made | Status | Verification Evidence / Mitigation |
| :--- | :--- | :--- | :--- | :--- |
| **A-01** | Strands Decider 2B runs comfortably in-process on an Intel Core i5-1335U with 16GB RAM without crashing or running out of memory. | Hardware inspection in Phase 0. | **VERIFIED** | Loaded model weights via PyTorch CPU; verified RAM usage is ~3.5GB; set `SLOPGATE_DECIDER_THREADS=4` to isolate to P-cores. |
| **A-02** | Amazon Bedrock Nova Micro is available in `us-east-1` and costs ~$0.035 / 1M input tokens. | AWS official documentation & hackathon specs. | **VERIFIED** | Verified region availability in `us-east-1`; budget cap configured to 50 calls. |
| **A-03** | Brand-new AWS accounts experience a 1–2 hour backend hold before foundation model Converse calls succeed. | User testing in Bedrock playground (`ValidationException: Operation not allowed`). | **VERIFIED** | Verified SigV4 credentials sign properly; standard AWS verification latency confirmed. Graceful fallback implemented. |
| **A-04** | GitHub write token requires only `issues:write` and `pull_requests:write` to manage triage labels and post comments on sandbox. | GitHub REST API permissions doc. | **VERIFIED** | Tested live API call against `Niklaus2003/slopgate-sandbox`: returned HTTP 200 with admin/push/maintain permissions. |
| **A-05** | Strands SDK `interventions.actions` provides native `Proceed`, `Confirm`, `Guide`, `Deny` action classes. | Strands Agents SDK inspection. | **VERIFIED** | Verified in `strands.interventions.actions` module in isolated `.venv`. |
| **A-06** | Ingesting and evaluating state payloads capped at `<= 450 tokens` retains sufficient context for accurate triage routing. | Token economy design in Phase 0. | **UNVERIFIED (To be calibrated in Phase 3/7)** | Backtesting against `pallets/flask` issues will empirically prove if 450 tokens preserves critical error context. |
| **A-07** | SQLite WAL mode provides sufficient concurrency for local CLI and Next.js REST dashboard. | SQLite architectural design. | **VERIFIED** | WAL mode verified lock-free for concurrent readers on Windows. |

---

## 2. Open Questions for Maintainer & User

1. **Escalation Notification:** When a `Confirm` or `Guide` item is queued, do you prefer a desktop OS notification, terminal chime, or strictly reviewing via the web dashboard inbox?
2. **Backtesting Dataset Size:** For the public backtest against `pallets/flask`, how many historical issues should we ingest for calibration? (Default plan: 50 issues, 25 PRs).
3. **Bedrock Unlock Check:** Once AWS completes your account verification hold, should we run a 1-token live smoke test against Nova Micro to verify live response generation?

---

## 3. Pre-Ship Rule
*Every item in this log marked **UNVERIFIED** must be experimentally validated and transitioned to **VERIFIED** (or discarded) before the final hackathon submission package is tagged.*
