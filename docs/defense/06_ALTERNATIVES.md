# ALTERNATIVES: SlopGate

> **Record of Rejected Options, Costs, and Trade-Offs.**
> Raw material for answering: *"Why did you do X instead of Y?"*
> Follows: *Defend What You Ship v2 (Section 05, Habit 17)*

---

## 1. Triage Intelligence Engine

| Approach | Summary | Why Rejected | Cost / What We Gave Up | Revisit If |
| :--- | :--- | :--- | :--- | :--- |
| **A: 100% Cloud LLM API** (Claude / GPT-4o) | Call Bedrock for every incoming issue/PR. | Expensive, requires internet, high token bill, unpredictable latency, no logit confidence calibration. | Gave up zero local memory overhead and immediate zero-setup cold boot. | Cloud LLM token costs drop to zero and local RAM is strictly restricted (<4GB). |
| **B: Pure Keyword & Heuristic Regex** | Static rules checking title length, keywords, checklists. | Brittle, fails on subtle PRs, cannot distinguish high-effort reports from AI-generated boilerplate. | Gave up sub-millisecond execution and zero memory requirements. | Hardware cannot run a 2B model at all. |
| **C: In-Process Decider 2B + Selective Escalation (CHOSEN)** | Strands Decider 2B on CPU handles routine cases; Bedrock Nova Micro called only for ambiguous cases. | **Selected:** Free local inference on CPU, calibrated confidence logits, fast triage (~300ms), 80%+ savings on API calls. | Requires ~4GB RAM to host model in memory. | N/A |

---

## 2. Decision Gating and Intervention Pattern

| Approach | Summary | Why Rejected | Cost / What We Gave Up | Revisit If |
| :--- | :--- | :--- | :--- | :--- |
| **A: Binary Threshold (Pass / Fail)** | If score > 0.8 approve, else close. | Binary filters alienate users, lack nuance, and violate the zero-auto-close safety rule. | Gave up simpler code (single `if/else`). | Problem requires strictly boolean classification with no human interaction. |
| **B: Custom Ad-Hoc If/Else Tree** | Scattered conditionals across worker files. | Untestable in isolation, unmaintainable, cannot be reused across projects, lacks audit receipts. | Gave up quick initial prototyping speed. | Never; ad-hoc logic causes unpredictable regression bugs. |
| **C: Reusable `ConfidenceBandHandler` (#policy) (CHOSEN)** | Formal 4-band intervention handler (`Proceed`, `Confirm`, `Guide`, `Deny`) with audit receipts. | **Selected:** Conforms to Strands Agents SDK intervention pattern, clean separation of policy from execution, fully testable, reusable across other triage pipelines. | Requires explicit state modeling and typed action planning. | N/A |

---

## 3. Persistent Storage Layer

| Approach | Summary | Why Rejected | Cost / What We Gave Up | Revisit If |
| :--- | :--- | :--- | :--- | :--- |
| **A: In-Memory Dict / Queue** | Store all items in Python heap. | Loses all triage state on process crash or reboot; no historic audit trail. | Gave up microsecond in-memory access. | Running strictly as a stateless lambda worker. |
| **B: PostgreSQL / Redis** | Run dedicated database containers. | Heavyweight, requires Docker and open ports, complex developer onboarding, unnecessary for single-maintainer workflow. | Gave up multi-server horizontal concurrency. | SlopGate is deployed as a multi-tenant cloud service. |
| **C: SQLite with WAL Mode (CHOSEN)** | Single file `slopgate.db` with Write-Ahead Logging and transactional integrity. | **Selected:** Built-in standard library, zero operations, ACID compliant, survives laptop restarts, enables concurrent reads during writes. | Not suitable for multi-node distributed clusters. | N/A |

---

## 4. Bedrock Foundation Model Selection

| Approach | Summary | Why Rejected | Cost / What We Gave Up | Revisit If |
| :--- | :--- | :--- | :--- | :--- |
| **A: Anthropic Claude 3.5 Sonnet** | Premium cloud LLM via Bedrock. | High token cost ($3.00/1M input, $15.00/1M output), exhausts developer free credits quickly. | Gave up top-tier multi-turn coding reasoning. | Maintainer has dedicated enterprise AWS credits. |
| **B: Meta Llama 3.1 70B** | Large open-weights model via Bedrock. | Moderate token cost ($0.72/1M), higher latency. | Gave up slightly more expansive vocabulary. | Nova Micro is unavailable in target region. |
| **C: Amazon Nova Micro (CHOSEN)** | Serverless foundation model (`amazon.nova-micro-v1:0`). | **Selected:** Ultra-low cost ($0.035/1M input), fast response time (~400ms), sufficient intelligence for drafting friendly triage guidance. | Shorter context window (compensated by our <=450 token state budget). | Maintainer needs autonomous multi-file code refactoring. |

---

## 5. User Interface & Operator Experience

| Approach | Summary | Why Rejected | Cost / What We Gave Up | Revisit If |
| :--- | :--- | :--- | :--- | :--- |
| **A: Pure CLI Only** | Terminal command line tool with rich tables. | Great for automation, but reviewing dozens of draft comments and diffs in a terminal is tiring for maintainers. | Gave up simplicity of a single binary/script. | Headless CI/CD server execution. |
| **B: Streamlit / Gradio** | Python-based quick prototyping UI. | Heavy server reruns, sluggish interactive state updates, hard to customize with polished modern aesthetics. | Gave up quick 10-line Python UI prototyping. | User needs a quick internal throwaway demo. |
| **C: Fast API + Next.js Maintainer Dashboard (CHOSEN)** | Local REST API (`slopgate serve`) feeding a sleek Next.js inbox dashboard (Phase 10). | **Selected:** Instant responsive UI, visual confidence meters, one-click maintainer approvals for `Confirm` items, interactive simulation playground. | Requires Node.js build step for web dashboard. | Maintainer explicitly requests a zero-node environment. |
