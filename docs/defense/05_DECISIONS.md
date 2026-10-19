# DECISIONS: SlopGate

> **Log of Key Architectural Decisions & Trade-Offs.**
> Answers the first whiteboard defense question: *"Why did you do X instead of Y?"*
> Follows: *Defend What You Ship v2 (Section 01, Habit 2 & Section 04, Habit 14)*

---

## D-001: Local In-Process Strands Decider 2B on CPU vs. Cloud LLM for Every Issue
- **Date:** 2026-10-15
- **Model:** Antigravity Agentic Claude 3.7
- **Context:** An open-source maintainer receives dozens to hundreds of incoming issues and PRs daily. Running a cloud LLM (e.g. Claude 3.5 Sonnet, GPT-4o) on every single submission is costly, exposes issue data to third parties, requires constant internet access, and introduces latency.
- **Options Considered:**
  1. *Cloud LLM API for 100% of issues:* Send all issues to Bedrock/Anthropic directly.
  2. *Pure heuristic regex rules:* Match keywords like "bug", "typo", "fix".
  3. *In-process Strands Decider 2B on CPU + Selective Bedrock Escalation:* Small calibrated model handles Q1/N1-N5 on CPU; Bedrock is called ONLY for ambiguous/low-confidence hard cases.
- **Chosen:** Option 3.
- **Why:** In-process inference runs free on local CPU in ~300ms, consumes zero API tokens for >80% of routine triage, and provides native logit-calibrated confidence scores. Bedrock is reserved for the 15-20% of submissions that actually need nuanced reasoning.
- **Trade-off:** Requires ~4GB RAM to load the model into memory and takes 3-5 seconds to warm up on the first run.
- **Revisit if:** Laptop hardware has less than 8GB RAM or maintainer demands zero local RAM footprint.

---

## D-002: ConfidenceBandHandler (#policy) 4-Band Gating vs. Custom Ad-Hoc If-Else
- **Date:** 2026-10-15
- **Model:** Antigravity Agentic Claude 3.7
- **Context:** The hackathon encourages creating reusable decision patterns tagged `#policy`. We need a principled mechanism to convert continuous probabilities/confidences into safe, auditable operational actions.
- **Options Considered:**
  1. *Ad-hoc if/else statements scattered across worker code.*
  2. *Two-state binary filter (Approve / Reject).*
  3. *Four-Band ConfidenceBandHandler (`Proceed`, `Confirm`, `Guide`, `Deny`):* Standardized Strands Agent intervention architecture.
- **Chosen:** Option 3.
- **Why:** Reusable, testable, and directly aligns with the Strands Agents SDK intervention lifecycle (`strands.interventions.actions`). It allows distinct behavioral paths: high confidence executes routinely (`Proceed`), medium prompts human confirmation (`Confirm`), low routes to Bedrock for helpful coaching (`Guide`), and safety violations halt (`Deny`).
- **Trade-off:** Slightly more boilerplate and structured typing required in data models.
- **Revisit if:** Strands SDK changes intervention protocol.

---

## D-003: SQLite WAL Mode vs. PostgreSQL / Redis
- **Date:** 2026-10-15
- **Model:** Antigravity Agentic Claude 3.7
- **Context:** We need a reliable persistence store for queued issues, decision receipts, and audit history that operates seamlessly on a developer laptop without complex setup.
- **Options Considered:**
  1. *In-memory Python dictionaries:* Zero persistence across restarts.
  2. *PostgreSQL or Redis container:* Requires Docker, open ports, external services.
  3. *SQLite in WAL (Write-Ahead Logging) mode with `PRAGMA synchronous = NORMAL`:* Single file, zero-ops, local ACID transactions.
- **Chosen:** Option 3.
- **Why:** Zero maintenance, embedded in Python standard library (`sqlite3`), no daemon needed, survives crashes, and supports concurrent read-while-write access via WAL mode.
- **Trade-off:** Not designed for multi-machine distributed horizontal scale (which is out of scope for a local maintainer CLI/dashboard).
- **Revisit if:** SlopGate is deployed as a multi-tenant SaaS service with multiple worker servers.

---

## D-004: Amazon Nova Micro on Bedrock vs. Claude 3.5 Sonnet
- **Date:** 2026-10-15
- **Model:** Antigravity Agentic Claude 3.7
- **Context:** When Bedrock escalation is triggered for ambiguous issues, we need a model that provides empathetic, specific contributor feedback while respecting free-tier credits and near-zero cost.
- **Options Considered:**
  1. *Claude 3.5 Sonnet / Haiku:* Excellent quality, but higher token cost ($3.00/1M or $0.25/1M).
  2. *Amazon Nova Micro (`amazon.nova-micro-v1:0`):* Fastest, lowest-cost serverless model on AWS Bedrock ($0.035 / 1M input tokens).
- **Chosen:** Option 2.
- **Why:** Nova Micro costs practically nothing ($0.000005 per triage call), fits well within AWS free credits ($200 promotional or standard credits last for tens of thousands of invocations), and is sufficiently intelligent for drafting friendly contributor guidance when given structured context.
- **Trade-off:** Shorter context window and slightly less complex multi-step reasoning compared to Claude 3.5 Sonnet, compensated by tightly constrained state inputs (<= 450 tokens).
- **Revisit if:** Feedback quality on complex code reviews proves insufficient in user testing.

---

## D-005: Zero Auto-Close Invariant vs. Automated Reject Thresholds
- **Date:** 2026-10-15
- **Model:** Antigravity Agentic Claude 3.7
- **Context:** Automated bots that close issues without human maintainer review cause immense frustration in open-source communities.
- **Options Considered:**
  1. *Auto-close items if confidence of "low quality" exceeds 0.95.*
  2. *Strict Zero Auto-Close Invariant:* All closures and rejections require human confirmation (`Confirm` verdict).
- **Chosen:** Option 2.
- **Why:** Preserves maintainer-contributor trust. Even if the decider is 99% confident an issue is low-quality, a human maintainer must click the confirm button. The bot drafts the response and sets the label, but never executes a closure autonomously.
- **Trade-off:** Maintainers must spend a few seconds reviewing flagged items in their queue instead of 100% full hands-off automation.
- **Revisit if:** Maintainer explicitly opts into auto-close with an external signed policy override (currently disabled by design).

---

## D-006: CPU PyTorch Wheels (`torch==2.14.1+cpu`) vs. Standard CUDA PyTorch
- **Date:** 2026-10-15
- **Model:** Antigravity Agentic Claude 3.7
- **Context:** Standard PyTorch installation bundles ~3GB+ of CUDA and cuDNN binaries even on machines without dedicated NVIDIA GPUs (e.g., Intel Iris Xe on Core i5-1335U).
- **Options Considered:**
  1. *Standard PyTorch via `pip install torch`:* Downloads 2.8GB-4GB CUDA binaries.
  2. *CPU-only PyTorch via `https://download.pytorch.org/whl/cpu`:* Downloads ~180MB CPU wheel.
- **Chosen:** Option 2.
- **Why:** Fast installation, minimal disk footprint, zero GPU driver compatibility issues, runs efficiently on modern 13th Gen Intel hybrid CPU architectures.
- **Trade-off:** Cannot accelerate inference on NVIDIA GPUs without reinstalling CUDA wheels.
- **Revisit if:** Maintainer runs SlopGate on a dedicated GPU workstation.

---

## D-007: Adoption of "Defend What You Ship v2" Framework
- **Date:** 2026-10-15
- **Model:** Antigravity Agentic Claude 3.7
- **Context:** Building with AI assistants can lead to context loss, untracked decisions, and unverified assumptions. We need an engineering methodology to ensure every line shipped is understood and defensible at a whiteboard.
- **Options Considered:**
  1. *Rely solely on Git commit messages and chat memory.*
  2. *Maintain the Defend What You Ship v2 documentation suite in `docs/defense/`.*
- **Chosen:** Option 2.
- **Why:** Guarantees continuity across sessions, explicitly records trade-offs and rejected alternatives, enforces safety invariants, and prepares the team for the four core whiteboard defense questions.
- **Trade-off:** Small overhead of updating documentation and running the pre-ship checklist at phase boundaries.
- **Revisit if:** Never; this is the core quality benchmark for the project.
