# FAILURE: SlopGate Resilience & Failure Modes Map

> **Comprehensive Analysis of System Failure Modes and Recovery Paths.**
> Answers: *"Where does this fail and how do we notice?"*
> Follows: *Defend What You Ship v2 (Section 05, Habit 19)*

---

## 1. Dependency-by-Dependency Failure Walk

### A. Amazon Bedrock (`amazon.nova-micro-v1:0`)

| Failure Condition | Immediate Symptom | System Handling / Graceful Degradation | Observability (How We Notice) |
| :--- | :--- | :--- | :--- |
| **New Account Hold** | `ValidationException: Operation not allowed` | Intercepted in client; logs an actionable message that the AWS account is undergoing 1-2hr verification; falls back to offline template response. | Terminal stderr banner; item flagged with `fallback_reason='bedrock_account_verification'`. |
| **Throttling / Rate Limit** | `ThrottlingException` (HTTP 429) | Exponential backoff (3 retries: 1s, 2s, 4s); if still failing, marks item as `PENDING_CONFIRMATION` without AI draft. | Logged in `receipts` table with `bedrock_called=0`; CLI prints yellow warning. |
| **Bedrock Outage / Network Drop** | `EndpointConnectionError` / Timeout | Times out after 10 seconds; does not hang the worker; item is safely saved to SQLite with status `PENDING_RETRY`. | Captured in `slopgate doctor` diagnostic check and CLI error log. |
| **Budget Cap Reached** | 50 calls exceeded in current session | Circuit breaker trips instantly; subsequent ambiguous items fall back to deterministic canned templates. | Terminal prints: `[BUDGET GUARD] Bedrock call limit reached (50/50). Escalations paused.` |

---

### B. GitHub REST API

| Failure Condition | Immediate Symptom | System Handling / Graceful Degradation | Observability (How We Notice) |
| :--- | :--- | :--- | :--- |
| **Rate Limit Exceeded (403)** | `x-ratelimit-remaining: 0` | Pauses execution; calculates sleep time until `x-ratelimit-reset` header; notifies user. | Header printed in doctor check; logged in CLI. |
| **Invalid / Expired Token (401)** | `Bad credentials` | Fails fast with clear instructions on generating a new token. | CLI error: `GitHub token invalid. Run 'slopgate doctor' to inspect.` |
| **Repository Not Found (404)** | `Not Found` | Skips item; logs warning; checks whether token has repo scope. | Warning in terminal output. |
| **Sandbox Write Permission Denied** | `Resource not accessible by integration` | Aborts mutation; falls back to dry-run mode and prints expected mutation diff. | Red error message in CLI output. |

---

### C. Local Strands Decider 2B (In-Process CPU)

| Failure Condition | Immediate Symptom | System Handling / Graceful Degradation | Observability (How We Notice) |
| :--- | :--- | :--- | :--- |
| **Model Weights Missing / Corrupt** | HuggingFace download failure / checksum mismatch | Fails during initialization; `slopgate doctor` detects missing cache and prompts download. | Clear error with command to download or run in `--mock` mode. |
| **Out-Of-Memory (OOM)** | Memory allocation error on low-RAM machine | Process would crash if payload is unbounded. **Prevented by design:** state builder enforces strict `<= 450 token` cap and batches are processed sequentially (batch size = 1). | Memory check in `slopgate doctor`. |
| **High Latency / Core Thrashing** | Single forward pass takes > 2 seconds | Caused by Intel hybrid P-core/E-core switching. **Mitigated:** `SLOPGATE_DECIDER_THREADS=4` limits execution to performance cores. | Latency recorded in milliseconds in every `DeciderResult`. |

---

### D. SQLite Database (`slopgate.db`)

| Failure Condition | Immediate Symptom | System Handling / Graceful Degradation | Observability (How We Notice) |
| :--- | :--- | :--- | :--- |
| **Database File Locked** | `sqlite3.OperationalError: database is locked` | SQLite configured with `timeout=30.0` and WAL mode (`PRAGMA journal_mode=WAL`), allowing concurrent readers without locking writer. | Logged if lock exceeds 30s timeout. |
| **Disk Full** | `sqlite3.OperationalError: disk I/O error` | Safe transaction rollback (`BEGIN TRANSACTION ... ROLLBACK`); uncommitted changes aborted cleanly. | Standard OS error reported in logs. |

---

## 2. The First Limits We Expect to Hit

1. **GitHub Unauthenticated Rate Limits (60 req/hr):**
   - Hit if `GITHUB_TOKEN` is unset and maintainer scans more than 60 issues.
   - *Fix:* `slopgate doctor` explicitly checks `GITHUB_TOKEN` and warns if missing.
2. **Bedrock Account Verification Hold (1–2 hrs):**
   - Hit on newly opened AWS accounts trying to call foundation models.
   - *Fix:* Automatic graceful fallback and informative diagnostics.
3. **Local Thread Contention:**
   - On 10-core / 12-thread laptop CPUs, spawning 12 threads causes thread synchronization overhead.
   - *Fix:* Hardcoded recommended thread default `SLOPGATE_DECIDER_THREADS=4`.

---

## 3. Observability & Health Checks

- **CLI Diagnostic Command:**
  ```powershell
  python -m slopgate.cli doctor
  ```
  Tests Python version, CPU threads, PyTorch CPU acceleration, environment variables, GitHub token rates, and Bedrock connectivity.
- **Audit Table (`receipts`):**
  Every triage decision produces a permanent SQLite row capturing item ID, confidence, band, verdict, Bedrock call status, and action plan JSON.
- **Exportable Decision Receipts:**
  ```powershell
  python -m slopgate.cli report --format markdown
  ```
  Generates a human-readable markdown audit trail of all actions and calibration scores.
