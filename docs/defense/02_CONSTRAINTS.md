# CONSTRAINTS: SlopGate

> **Hard Boundaries and Non-Negotiable Rules.**
> These boundaries govern every line of code written by humans or AI.
> Follows: *Defend What You Ship v2 (Section 02, Habit 7 & Section 06, Habit 22)*

---

## 1. Hard System Invariants (NEVER violate)

| Rule | Statement | Rationale |
| :--- | :--- | :--- |
| **INVARIANT 1** | **NEVER auto-close any GitHub issue or PR.** | Closing user contributions without human maintainer sign-off alienates contributors and damages open-source communities. Rejection actions strictly produce `Confirm` verdicts requiring maintainer click. |
| **INVARIANT 2** | **NEVER accuse a contributor of using AI or producing "slop".** | Feedback must always be empathetic, specific, and actionable (e.g. asking for minimal reproduction, missing test cases, or clarification of intent) regardless of how low-effort the submission appears. |
| **INVARIANT 3** | **NEVER execute in-process decider inference on GPU or cloud servers.** | Strands Decider 2B runs locally on the maintainer's CPU to ensure zero compute cost, absolute privacy, and offline capability. |
| **INVARIANT 4** | **NEVER exceed 50 Amazon Bedrock calls per run.** | Strict circuit breaker ensures zero chance of accidental cost overruns. Once the cap is hit, remaining items default to local-only heuristic routing. |
| **INVARIANT 5** | **NEVER write live mutations to non-sandbox repositories.** | Live GitHub actions (`issues:write`, `pull_requests:write`) are permitted ONLY when targeting `GITHUB_SANDBOX_REPO` and with `SLOPGATE_DRY_RUN=0`. All other operations default to simulation. |
| **INVARIANT 6** | **NEVER commit secrets, tokens, credentials, or private docs to Git.** | `.env`, `docs/`, and `scripts/` are strictly gitignored. All AWS/GitHub credentials must stay exclusively on the local machine. |

---

## 2. Protected Code Areas

The following modules contain mission-critical safety logic and must never have checks removed or loosened:

1. **`src/slopgate/policy/gate.py` (`ConfidenceGate`)**:
   - The safety rule that downgrades any `close_item` action to `Confirm` must NEVER be bypassed or made optional.
2. **`src/slopgate/policy/resolver.py` (`ActionResolver`)**:
   - Resolution precedence MUST remain strictly deterministic: `DENY > CONFIRM > GUIDE > PROCEED`.
3. **`src/slopgate/bedrock/client.py`**:
   - Hard call counter and budget check before every Converse call.
4. **`src/slopgate/config.py`**:
   - Ambient token sanitization logic preventing botocore SigV4 disruption.

---

## 3. Least Privilege Allow Policy (Habit 22)

### AUTO-ALLOW (Safe Actions)
- Reading local source files and markdown documentation.
- Running unit test suite (`pytest`) and linters (`ruff`).
- Executing pure Python logic on CPU.
- Querying SQLite in read-only mode.
- Fetching public GitHub issue/PR metadata via GET requests.

### PAUSE AND CONFIRM (Requires Review)
- Modifying database schemas or migrations.
- Adding a new external Python dependency to `requirements.txt`.
- Changing confidence threshold constants (`HIGH >= 0.85`, `LOW <= 0.60`).
- Updating prompt templates for Bedrock Nova Micro.
- Running live mutating API calls against GitHub sandbox repository.

### NEVER ALLOW (Strictly Prohibited)
- Storing credentials in plain text in any committed file.
- Auto-closing issues or PRs without maintainer confirmation.
- Bypassing the confidence band resolver.
- Running CUDA/GPU PyTorch on this machine.
- Granting AI blanket write access to production open-source repositories.
