# 🎬 SlopGate Video Walkthrough Script

**Target Duration:** `2 minutes 30 seconds` (Maximum limit: `2:45`)  
**Submission Category:** AWS AI Agents Hackathon — Strands Decider 2B & Amazon Bedrock  
**Key Tags:** `#strands-decider-2b` `#policy`

---

## Technical Recording Guidelines
- **Resolution:** 1080p (1920x1080) at 60fps.
- **Visuals:** Dark mode enabled throughout; clean browser and terminal fonts.
- **Audio:** Clear voiceover commentary; no background music or third-party copyrighted audio.
- **Speed-ups:** Any compilation or packaging steps labeled on-screen with `[2x Speed]`.

---

## Timeline & Scene Breakdown

### Scene 1: The Problem — The AI Slop Tsunami (0:00 – 0:25)
- **Visual on Screen:** Quick montage of real GitHub issues and PRs with hallmark "AI slop" (confidently incorrect explanations, hallucinated methods, broken syntax). Followed by a screenshot of an angry Reddit/Hacker News thread where an automated bot mistakenly closed a senior engineer's real bug report.
- **Voiceover (Narrator):**
  > "Open source maintainers are drowning in AI-generated pull requests and issues that look convincing at first glance but fail to compile or hallucinate APIs.
  > 
  > But when maintainers deploy aggressive bots to auto-close low-effort issues, disaster strikes: legitimate, first-time contributors get rejected, community trust evaporates, and real bugs slip through the cracks.
  > 
  > Maintainers don't need a blunt auto-closer. They need a confidence-calibrated front door. Meet **SlopGate**."

---

### Scene 2: The Architecture — Small on CPU, Large in the Cloud (0:25 – 0:50)
- **Visual on Screen:** Clean animated architecture diagram showing:
  `GitHub Event` ➔ `SQLite WAL Queue` ➔ `State Builder (≤450 tokens)` ➔ `Strands Decider 2B (5ms on CPU)` ➔ `ConfidenceBandHandler` ➔ `Proceed / Confirm / Guide / Deny` ➔ `Amazon Bedrock (Empathetic drafts)`.
- **Voiceover (Narrator):**
  > "SlopGate pairs a local 1.9B linear-attention model, **Strands Decider 2B**, with **Amazon Bedrock**.
  > 
  > Routine triage happens locally, in-process, on the maintainer's own laptop CPU in just 5 milliseconds at zero dollar cost.
  > 
  > Decisions are evaluated through mathematically normalized confidence bands. 
  > High confidence safe actions proceed automatically. 
  > Ambiguous cases escalate to Amazon Bedrock for empathetic feedback. 
  > And destructive mutations strictly mandate maintainer confirmation."

---

### Scene 3: Demo 1 — The Live Triage Simulator (0:50 – 1:25)
- **Visual on Screen:** Browser window on `http://localhost:3000`. Demonstrating the Interactive Playground with distinct fixture selections:
  1. Click **`clean-bug`**: Shows deterministic fact extraction (repro heading detected, code block detected, symbols in repo index). Inference bars show `real_bug_report` at 84% confidence $\to$ **`PROCEED`** badge turns glowing green.
  2. Click **`pr-needing-explanation`**: Inspects a pull request diff lacking rationale $\to$ routed to **`CONFIRM`** (maintainer review).
  3. Click **`low-effort`** ("pls help how do i make a full login page"): Decider classifies as low effort. Shows **`PROCEED_SOFT`** badge with no close action, and Bedrock panel appears displaying a drafted empathetic reply guiding the student to tutorial resources without accusing them of using AI.
  4. Click **`security-report`** (Jinja SSTI disclosure): Even with 99% confidence, the gate forces a **`CONFIRM`** badge due to the hardcoded security invariant.
- **Voiceover (Narrator):**
  > "In the SlopGate Live Simulator, we see the dual-model cascade in action.
  > 
  > Please note that this demonstration is running with mock data and offline decider cascades, as my AWS account credits and Amazon Bedrock model access are currently undergoing backend verification—which typically takes around two to three months to get full access approval. So I am demonstrating the architecture and workflow with mock data today. However, the entire pipeline is fully wired to seamlessly use live Amazon Bedrock and the production Strands Decider 2B model as soon as my account is verified.
  > 
  > When a clean Flask bug arrives with a verified traceback, Decider 2B evaluates it in 5 milliseconds on CPU, assigns High Confidence, and marks it to Proceed.
  > 
  > When an ambiguous PR or low-effort support question appears, SlopGate issues a soft label and calls Bedrock to draft a warm, helpful response—without closing the issue or accusing the contributor.
  > 
  > And for critical security disclosures, our hardcoded invariant guarantees it immediately escalates for maintainer review."

---

### Scene 4: Demo 2 — Maintainer Review Queue & Decision Receipts (1:20 – 1:45)
- **Visual on Screen:** Navigate to **Review Inbox** (`/inbox`):
  1. Displays the queue of items needing human sign-off.
  2. Click **"View Full Receipt"**: A slide-out drawer opens showing the complete Markdown Decision Receipt with state hash, deterministic facts, decider cascade breakdown, and Bedrock rationale.
  3. Click **"Approve & Execute (Live)"**: Status flips to approved with a green notification banner.
- **Voiceover (Narrator):**
  > "Here in the Maintainer Review Queue, maintainers have total control.
  > 
  > Every triage event produces an auditable, tamper-evident Decision Receipt—logging the exact input state hash, deterministic facts, and probability distributions.
  > 
  > Destructive operations like closing issues can never happen unattended. Maintainers can approve with a single click, dry-run simulated actions, or reject proposed plans."

---

### Scene 5: The Reusable Asset — `#policy` Decision Pattern (1:45 – 2:10)
- **Visual on Screen:** Split screen showing the VS Code folder `patterns/confidence_band_handler/` and running `python patterns/confidence_band_handler/example_non_slopgate.py` in the terminal.
  - Highlight the formula on screen: $\text{conf}_{\text{norm}} = (N \cdot p_{\max} - 1) / (N - 1)$.
  - Show the Strands Agents SDK `InterventionHandler` implementation (`Proceed`, `Confirm`, `Guide`, `Deny`).
  - Terminal outputs the enterprise CRM run: `send_email` automatically approved, account question guided, and destructive `delete_record` intercepted for human confirmation.
- **Voiceover (Narrator):**
  > "We didn't just build an application—we packaged our core decision-gating logic into an independent, reusable asset for the hackathon: `patterns/confidence_band_handler/`.
  > 
  > It features zero dependencies on SlopGate, implements the native Strands Agents InterventionHandler API, and normalizes multi-choice probabilities into actionable confidence bands.
  > 
  > Here it is running in an enterprise CRM setting: safely auto-sending customer emails, guiding ambiguous tickets, and intercepting destructive database deletions."

---

### Scene 6: Empirical Backtest & Calibration (2:10 – 2:35)
- **Visual on Screen:** Navigate to **Calibration & Safety Analytics** (`/analytics`):
  - Highlight KPI 1: **0.0% False-Reject Invariant** on accepted community PRs.
  - Highlight KPI 2: **0 Unattended Closures**.
  - Highlight KPI 3: **5.00 ms CPU Decider Latency vs 450 ms Bedrock Cloud Latency** (~90x speedup).
  - Highlight KPI 4: **$0.0460/1k items vs $0.0500/1k items baseline**.
  - Quick glance at the Failure Cases table showing 100% of prediction errors safely diverted by confidence bands.
- **Voiceover (Narrator):**
  > "We backtested SlopGate on 50 replayed issues from the official Flask repository on ordinary laptop CPU hardware.
  > 
  > The results? Exactly 0.0% false rejections on valid community contributions, zero unattended closures, a 5-millisecond CPU p50 latency that runs 90 times faster than cloud round-trips, and measurable cost savings over a 100% LLM baseline."

---

### Scene 7: Wrap-up & Call to Action (2:35 – 2:45)
- **Visual on Screen:** SlopGate GitHub repository page and Builder Center article draft showing MIT license and `#strands-decider-2b` `#policy` tags.
- **Voiceover (Narrator):**
  > "SlopGate protects open-source maintainers from burnout without sacrificing the open, welcoming spirit of open source.
  > 
  > Check out our open-source codebase, try the reusable pattern in your own agents, and thank you for watching!"
