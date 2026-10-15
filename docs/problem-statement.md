# SlopGate — Project Brief for the Coding Agent

> **One-line pitch:** A local, CPU-only, confidence-gated front door for open-source maintainers. A small decision model (Strands Decider 2B) triages incoming issues and PRs for free on the maintainer's own laptop; Amazon Bedrock is called only for the hard cases and for writing kind, specific replies. It never auto-closes anything.

**Read this whole file before writing any code.** It contains the context, constraints, design decisions, and acceptance criteria. Where this file says "verify," do not guess: read the source or run a command and confirm.

---

## 0. How you (the coding agent) should work

1. **Do not invent APIs.** Strands Decider, the Strands Agents SDK, and its `InterventionHandler` are new. Before using them, read the official sources listed in section 14 and run small experiments. If an import path or method name here conflicts with what you observe, trust what you observe and tell the user.
2. **Everything must run for free on a CPU-only machine.** No GPU assumptions, no paid services beyond the Bedrock free-tier credits, no paid SaaS.
3. **Never write to a real third-party GitHub repository.** Default mode is dry-run. Live writes are only for the user's own sandbox demo repo.
4. **Never commit secrets.** AWS credentials, GitHub tokens, and Bedrock keys come from environment variables or a git-ignored `.env`.
5. **Do not claim numbers you did not measure.** Every accuracy, latency, and cost figure in the README and article must come from a script in the repo.
6. **Build in priority order** (section 12). A working P0 end-to-end beats a half-finished P2.
7. **Ask the user** (once, early) the things in section 15.

---

## 1. Context: the hackathon this project is for

- **Event:** Strands Decider Agent Hackathon (AWS Builder Center).
- **Submission window:** Oct 16, 2026, 9:00 a.m. PT → **Oct 23, 2026, 11:59 p.m. PT**.
- **Goal:** build a working agent on AWS that uses **Strands Decider 2B** for at least one meaningful decision, **paired with Amazon Bedrock** for the generative part.
- **Pass/fail qualification (all required):**
  1. A written article published on AWS Builder Center describing the agent and the decision handed to Decider 2B.
  2. A **public** repo (OSI-approved license) containing the agent's source **and at least one clearly labeled, reusable Decider 2B decision pattern**: the typed question(s) and option set, the wiring that places the decision in the agent's path (e.g., a Strands `InterventionHandler`), and a short usage note.
  3. A public demo video, **under 3 minutes**, showing the agent and its Decider decision working (YouTube/Vimeo/Facebook Video/Youku). No third-party trademarks or copyrighted music.
- **Tags:** `#strands-decider-2b` and exactly one pattern tag. Ours: **`#policy`**.
- **Must be original and not previously published.** Precaution: keep the repo private until it is ready to submit, then make it public before the deadline.
- **Judging weights:** Creativity/cool factor 30%, Effective use of Decider 2B with Bedrock (including reusable-pattern quality; a measured latency/cost improvement is a bonus) 30%, Communication quality 25%, Originality 15%.

Design every decision below with those weights in mind.

---

## 2. The problem

Open-source maintainers are being flooded with low-effort, poorly grounded issues, bug reports, and pull requests. Volume has grown far faster than the number of reviewers. Documented examples:

- curl closed its HackerOne bug bounty (Jan 2026) after being swamped by low-quality, often AI-influenced security reports.
- tldraw began auto-closing all external PRs (Jan 2026).
- GitHub's product team opened a community discussion (Feb 2026) on the rising volume of low-quality contributions, and GitHub's own blog notes maintainers asking how to sift noise from important contributions.
- An ACM Technology Policy Council TechBrief (Sept 15, 2026) argues AI is both improving open source and overwhelming the volunteer structures sustaining it.
- Projects such as Ghostty, Kubernetes, Django, LLVM, and others have introduced disclosure or contribution policies.

**Why current responses are inadequate:**

- They are blunt: ban everything, close the gate, or remove incentives. Good newcomers get caught in the net.
- Using an LLM to triage every item is costly and slow, and volunteers cannot pay for it.
- Existing classifiers give an answer without saying how sure they are, so a maintainer cannot tell which decisions to trust.

**What is missing:** a cheap, local, *calibrated* middle layer that handles the routine decisions itself, knows when it is unsure, and hands only those cases to a human or a larger model.

### Target user

A solo or small-team open-source maintainer on a normal laptop (no GPU) with a limited budget, who wants less triage drudgery without handing control to an opaque bot.

---

## 3. Solution overview

SlopGate watches a repository's incoming issues and PRs and, for each item:

1. Builds a **compact state** (a short text summary + deterministic facts extracted by plain code).
2. Asks **Strands Decider 2B** a small set of **typed questions** (choice and yes/no) and gets answers with calibrated confidence, locally on CPU.
3. Maps (answer, confidence) through a **confidence-band policy** to an action: **Proceed, Confirm, Guide, or Deny**.
4. Calls **Amazon Bedrock** only when needed: (a) to write a kind, specific, actionable reply, and (b) to reason about low-confidence items.
5. Records a **decision receipt** for every item (what was asked, what was answered, how confident, why it was routed that way).
6. Never closes or rejects anything without a human.

### Design principles (non-negotiable)

- **Judge effort and grounding, not authorship.** Never claim to detect "AI-written" content. That is unreliable and unfair. Questions are about concrete detail, reproducibility, relevance, and policy compliance.
- **Protect newcomers.** A low-confidence or ambiguous result must lead to a human or a helpful reply, never a rejection. Author-history signals (account age, prior merges) are **excluded from the Decider state by default** and available only as an opt-in config flag.
- **Never auto-close.** The `close_item` tool must always be `Confirm`-gated by the handler regardless of confidence.
- **Calibration is the feature.** The demo and article are about *knowing when it isn't sure*.
- **Cost-aware.** Decider runs free and locally. Bedrock calls are capped by a configurable budget guard.

---

## 4. Strands Decider 2B primer (what you need to know)

- Open, experimental decision model from Strands Labs (AWS). ~1.9B parameters, Qwen3.5-2B-Base + LoRA + a pointer/readout head. It **does not generate text**: it scores the supplied options in one forward pass.
- Current reference checkpoint: `StrandsAgents/strands-decider-2B-hobson-v21` (v19 remains published).
- **Three question types** (same mechanism, read back differently):
  | Type | Options | Returns |
  |---|---|---|
  | `noul` | yes/no | P(true). No separate confidence: the probability *is* the uncertainty. |
  | `choice` | 2..N options | argmax, per-option probabilities, confidence |
  | `score` | 2..10 ordered levels | expected level, distribution, confidence |
- **Confidence for choice:** `(N·p_max − 1)/(N − 1)` → 0 for uniform, 1 for certain, comparable across different N. One threshold therefore means the same thing for 3 or 10 options.
- **Install/run:**
  ```bash
  pip install strands-decider
  strands-decider ask StrandsAgents/strands-decider-2B-hobson-v21 --device cpu \
    --state "..." --choice "Which team?=billing,sales,retail" --noul "Is this urgent?"
  strands-decider serve StrandsAgents/strands-decider-2B-hobson-v21 --port 8000
  ```
  Python: `strands_decider.modeling.StrandsDeciderModel.load("StrandsAgents/strands-decider-2B-hobson-v21")`. Base weights download from the Hugging Face Hub on first use.
- **Known limits (design around them, and report them honestly):**
  - ~72% on JevBench's public set. It is *not* a highly accurate model, so confidence gating is the point.
  - Upstream finds that on tasks unlike its training data, **choice questions are usable behind a confidence threshold, and score questions are not.** → **Do not use `score` questions for decisions in this project.**
  - With the state and options fixed, a changed question wording often returns the same answer. **Phrase each question so the obvious reading is the intended one**, and test wording variants in the backtest.
- **CPU performance (reported):** ~1.6 s per question on an 8-thread Xeon for short input; ~16–18 s at ~3,000 tokens. Many questions about the same text are cheap because the text is read once. → **Keep state ≤ ~450 tokens and cascade questions.**
- Decision models complement the LLM; they don't replace it.

---

## 5. Architecture

```
GitHub (public repo)                       Local machine (CPU only)
  issues / PRs ──► Ingestor ──► SQLite queue ──► Worker
                    (REST,                          │
                     etag/since)                    ▼
                                             State Builder
                                   (truncate + deterministic Fact Extractors)
                                                    │
                                                    ▼
                                  Decision Cascade ── Strands Decider 2B (local, CPU)
                                                    │      choice / noul + confidence
                                                    ▼
                                    Strands Agent (tools below)
                                  ┌─────────────────────────────────┐
                                  │ ConfidenceBandHandler            │  ← reusable pattern
                                  │ (InterventionHandler.before_tool_call)
                                  │  Proceed / Confirm / Guide / Deny│
                                  └─────────────────────────────────┘
                                         │            │
                          Proceed: label/templated    Guide/low-conf: escalate
                          comment (dry-run default)         │
                                         │                  ▼
                                         │        Amazon Bedrock (small model)
                                         │   - reasoning on ambiguous items
                                         │   - kind, specific reply drafts
                                         ▼
                               Decision Receipts + Calibration Report
                               (SQLite → JSON/Markdown/HTML)
```

### Components

| Component | Responsibility |
|---|---|
| `ingest/` | Pull issues/PRs from the GitHub REST API (token optional; unauthenticated rate limits are low). Supports `--since`, ETag caching, and a **replay mode** reading a saved JSON dump (for backtests and demos). |
| `state/builder.py` | Build the compact state string (see 6.1). Enforces the token cap. |
| `state/facts.py` | Deterministic, cheap fact extractors (see 6.2). Plain code, no models. |
| `decider/client.py` | Thin wrapper over Decider (in-process `StrandsDeciderModel` or the local `serve` endpoint, whichever is simpler once verified). Returns typed results with latency. Loads the model **once**. |
| `decider/questions.py` | The typed question definitions (section 7). Single source of truth. |
| `decider/cascade.py` | Runs Q1, then conditional follow-ups; early exit when confident. |
| `policy/bands.py` | Pure function: `(question, answer, confidence/prob, policy.yaml) → Band` where Band ∈ {HIGH, MEDIUM, LOW}. |
| `agent/tools.py` | Strands tools: `fetch_item`, `apply_label`, `post_comment`, `request_info_comment`, `close_item`, `flag_for_maintainer`. All write tools respect dry-run. |
| `agent/handler.py` | **`ConfidenceBandHandler`**: the reusable `InterventionHandler` (section 8). |
| `bedrock/escalate.py` | Bedrock calls: `reason_on_ambiguous()` and `draft_reply()`. Budget guard included. |
| `store/db.py` | SQLite: items, decisions, actions, escalations, receipts. |
| `report/` | Decision receipts (JSON + Markdown), calibration report (accuracy by confidence band, coverage, false-reject rate, latency, cost), optional single-file HTML. |
| `api/server.py` | Local REST API (`slopgate serve`) providing JSON endpoints for items, triage execution, approvals, and calibration analytics. |
| `web/` | Modern Next.js frontend dashboard with live Triage Simulator, Maintainer Review Inbox, and visual calibration charts. |
| `cli.py` | `slopgate ingest | run | review | backtest | report | serve | demo`. |

---

## 6. State and facts

### 6.1 State format (cap ≈ 450 tokens; enforce with a tokenizer if available, else ~1,800 characters)

```
[TYPE] issue | pull_request
[TITLE] <title>
[BODY] <first ~1200 chars, whitespace-collapsed>
[FILES] <N changed; up to 10 paths>            (PRs only)
[DIFF] +<added> -<removed>                      (PRs only)
[FACTS]
- cited_paths_found: 1 of 3
- has_code_block: yes
- has_repro_heading: no
- template_sections_filled: 1 of 4
- links_to_issue: none
- ci_status: failing | passing | unknown
- candidate_duplicate: #123 (similarity 0.71) | none
- contributing_summary: <one-line excerpt of relevant CONTRIBUTING rule, if any>
```

Rules:
- **Never** put raw diffs in the state. CPU latency grows sharply with length.
- Facts are the bridge between hard evidence and the fuzzy decision. They let the tiny model judge *grounding* without having to look things up.
- Exclude author-history facts unless `include_author_history: true` in policy.

### 6.2 Fact extractors (deterministic)

- **cited_paths_found:** regex-extract file paths, function/class names, and API identifiers from the text; check them against the repo file tree / symbol index (a cached `git ls-files` plus a simple `ctags`-style or grep index of top-level definitions). Report `found of cited`.
- **has_code_block / has_repro_heading / template_sections_filled:** parse markdown; compare against the repo's issue/PR template headings.
- **links_to_issue:** `#123`, `fixes #123`, full issue URLs.
- **ci_status:** GitHub checks API (PRs); `unknown` if unavailable.
- **candidate_duplicate:** local lexical similarity (TF-IDF or BM25, e.g., `scikit-learn` or `rank_bm25`) against recent open+closed items. No paid embeddings. Include top candidate and score.
- **contributing_summary:** simple keyword match against `CONTRIBUTING.md` sections.

Document the limitation that paths are checked against the default branch HEAD, not the item's creation time.

---

## 7. The typed questions (Decider's decisions)

**Use only `choice` and `noul`. No `score`.** All questions live in `decider/questions.py` and are exported to `patterns/` for reuse.

### Q1 — Item kind (choice), asked for every item

For `issue`:
- `real_bug_report`: reports a specific problem with enough detail to investigate
- `feature_request`: asks for new behavior
- `support_question`: asks how to use the software
- `likely_duplicate`: repeats an existing known problem
- `security_report`: describes a possible vulnerability
- `low_effort`: lacks concrete detail, reproduction, or a clear purpose

For `pull_request`:
- `ready_for_review`: clear purpose, scoped change, follows guidelines
- `needs_work`: reasonable purpose but missing explanation, tests, or guideline compliance
- `out_of_scope`: change unrelated to the project's goals or to an accepted issue
- `low_effort`: unclear purpose, unrelated or trivial churn, or no explanation

Question text (draft, **tune in backtest**): *"Based on the item and the facts, which description best fits this contribution?"*

### Conditional yes/no follow-ups (noul)

| ID | Asked when | Question |
|---|---|---|
| N1 | Q1 = `real_bug_report` | "Does the text include concrete steps or code that would let a maintainer reproduce the problem?" |
| N2 | Q1 ∈ {`real_bug_report`, `ready_for_review`} | "Do the specific files, functions, or APIs named in the text appear in the repository facts?" |
| N3 | item is a PR and Q1 ≠ `low_effort` | "Does the description explain why the change is needed, not only what it changes?" |
| N4 | `candidate_duplicate` fact present with similarity ≥ policy threshold | "Is this the same underlying problem as the candidate duplicate listed in the facts?" |
| N5 | CONTRIBUTING fact present | "Does the item follow the contribution guideline quoted in the facts?" |

**Cascade rule:** If Q1 is HIGH confidence and the label is a clearly fine outcome (e.g., `real_bug_report` with N1 true), stop early. Ask only the follow-ups the next action needs. This saves CPU time.

---

## 8. Confidence-band policy and the reusable pattern

### 8.1 Bands (initial values; tune from the backtest, store in `policy.yaml`)

- **choice:** HIGH ≥ 0.80, MEDIUM 0.50–0.80, LOW < 0.50 (confidence as defined in section 4).
- **noul:** TRUE-confident P(true) ≥ 0.85; FALSE-confident P(true) ≤ 0.15; otherwise UNCERTAIN.

### 8.2 Action matrix

| Situation | Band action | What happens |
|---|---|---|
| `real_bug_report` HIGH + N1 true | **Proceed** | Label `triaged`. No comment. |
| `real_bug_report` HIGH + N1 false (confident) | **Proceed** | Label `needs-info`; templated or Bedrock-drafted "please add reproduction steps" comment. |
| `support_question` HIGH | **Proceed** | Label `question`; templated redirect to Discussions/docs. |
| `likely_duplicate` + N4 true | **Confirm** | Suggest label + link to original; maintainer approves. Closing is never automatic. |
| `low_effort` HIGH | **Proceed (soft)** | Label `needs-more-detail`; Bedrock-drafted kind, specific comment explaining what's missing. **No close.** |
| `security_report` (any confidence) | **Confirm** | Flag to maintainer; comment (if any) points to private disclosure policy. Never public analysis. |
| `ready_for_review` HIGH | **Proceed** | Label `ready-for-review`. |
| MEDIUM anywhere | **Confirm** | Receipt shown to maintainer with suggested action; one-click approve/reject. |
| LOW anywhere / UNCERTAIN | **Guide** | Agent is guided to escalate to Bedrock for reasoning; result then goes to **Confirm**. |
| Any `close_item` call | **Deny** unless maintainer-approved | Handler enforces regardless of confidence. |

### 8.3 `ConfidenceBandHandler` (the required reusable asset)

A Strands `InterventionHandler` implementing `before_tool_call`. Per the Strands Decider repo's example, the handler returns a typed action: **Proceed, Deny, Confirm, or Guide**.

Requirements:
- **Verify the exact import paths, class names, and return types** by reading `examples/strands/` in `strands-labs/strands-decider` and the Strands Agents docs. Start from that example; do not write it from memory.
- Configuration is data-driven (`policy.yaml`): which tools are gated, which question each gate asks, thresholds, and the mapping band → action.
- Handler logic: for a tool call, build/fetch the state, run the relevant Decider question(s) (cached by state hash), compute the band, return the action, and write a receipt.
- It must be **repo-agnostic**: no GitHub-specific code inside the handler. SlopGate-specific questions are passed in as config.

Deliver it as a standalone pattern folder:

```
patterns/confidence_band_handler/
  README.md          # what it does, when to use it, 5-minute quickstart
  handler.py         # the InterventionHandler
  bands.py           # pure band logic (unit-tested)
  policy.example.yaml
  example_agent.py   # minimal agent using it with a toy tool (e.g., send_email gate)
  tests/
```

README "recipe card" must contain: the typed question and option set, the wiring snippet, threshold guidance, and the "when confidence is low" behavior.

**Optional second pattern** (only if time allows): `patterns/grounding_check/`, a yes/no question that checks whether claims are supported by extracted facts.

---

## 9. Amazon Bedrock usage

Bedrock is for **generation and hard reasoning only**.

1. `draft_reply(item, decision_receipt) → str`: kind, specific, actionable comment, ≤ ~120 words. Requirements for the system prompt: no accusations, never mention or speculate about AI authorship, name exactly what is missing, link to the relevant CONTRIBUTING section, offer a concrete next step, thank the contributor.
2. `reason_on_ambiguous(item, facts, decider_probs) → {suggested_label, rationale}`: used for LOW/UNCERTAIN cases. Output goes to Confirm, never straight to action.

Requirements:
- Use the Strands Agents SDK's Bedrock model provider where practical, or `boto3` Bedrock Runtime. **Model ID comes from config/env** (`BEDROCK_MODEL_ID`, `AWS_REGION`). Do not hardcode. Verify which small model is enabled for the user's account/region.
- **Budget guard** (config): `max_bedrock_calls_per_run`, `max_output_tokens`, `max_input_chars`, and a hard stop that logs and falls back to "flag for maintainer" when exceeded.
- Log input/output token counts per call for cost reporting. Prices live in config (not hardcoded).
- Templated replies for common high-confidence cases should avoid Bedrock calls entirely.
- Credentials via standard AWS env vars/profile (or a Bedrock API key in env). Never commit them.

**Free-tier context:** new AWS accounts on the Free plan get credits (reported as $100 plus up to $100 more from using services like Bedrock) that last 6 months or until used. Design for a few dollars of total usage.

---

## 10. Storage, receipts, and reporting

### SQLite tables (minimum)

- `items(id, repo, number, type, title, created_at, state_hash, raw_json)`
- `decisions(id, item_id, question_id, qtype, answer, probs_json, confidence, band, latency_ms, model_id, created_at)`
- `actions(id, item_id, tool, args_json, handler_result, dry_run, created_at)`
- `escalations(id, item_id, bedrock_model, tokens_in, tokens_out, latency_ms, est_cost_usd, purpose)`
- `ground_truth(item_id, label, source)`: for backtests.

### Decision receipt (per item; JSON + rendered Markdown)

```
Item: owner/repo#123 (issue)
State hash: ab12…  | Decider: strands-decider-2B-hobson-v21 (CPU) | 4.1 s total
Q1 kind → low_effort  (confidence 0.86, HIGH)
N1 repro steps? → P(true)=0.07 (FALSE-confident)
Routing: Proceed (soft): label needs-more-detail; Bedrock draft attached
Bedrock: 1 call, 612 in / 94 out tokens
Human approval required to close: YES (always)
```

### Calibration report (the evidence for the article)

From the backtest, produce: accuracy by confidence band; share of items handled without Bedrock (coverage); escalation rate; **false-reject rate on good items** (the key safety metric); p50/p95 seconds per item on this CPU; tokens and estimated cost vs a **Bedrock-only baseline** run on the same subset; and effect of question-wording variants. Include the machine spec (CPU model, cores, RAM) in the report header.

---

## 11. CPU performance rules

- Load the model **once** at worker start. Never spawn the CLI per item.
- Set torch/threads to the physical core count; document it.
- Cap state length; cascade questions; early exit.
- Cache decisions by `(state_hash, question_id, model_id)`.
- Process in a **background queue**; do not promise real-time. Report honest per-item latency measured on this machine.
- During the backtest, other heavy applications should be closed.
- **Decision rule:** if one item takes > ~10 s with a ~400-token state, reduce the state to ~250 tokens and cut to one choice + two noul questions. Do **not** swap to a different model; the hackathon requires Decider 2B.

---

## 12. Build order and milestones (today is Oct 15; deadline Oct 23, 11:59 p.m. PT)

**P0: must exist for submission**
1. Environment + smoke test: install `strands-decider`, run `ask` on CPU with a real issue, record seconds/question. Report to the user.
2. Ingestor with replay mode; SQLite schema.
3. State builder + fact extractors.
4. Decider client + Q1 + N1/N2 + cascade.
5. `ConfidenceBandHandler` + Strands agent with tools in **dry-run**.
6. Bedrock `draft_reply` + budget guard.
7. Decision receipts.
8. Backtest runner + calibration report (150–200 items).
9. `patterns/confidence_band_handler/` with README and tests.
10. Public-ready repo: README, LICENSE (MIT or Apache-2.0), requirements, quickstart.

**P1: strongly improves score**
11. Duplicate detection (N4) and `reason_on_ambiguous`.
12. Question-wording variant experiment.
13. Sandbox demo repo with seeded items + `slopgate demo` command.
14. Next.js interactive dashboard (`web/`) & local API (`slopgate serve`): live Triage Simulator, maintainer review inbox, and visual calibration charts (key asset for demo video & article).

**P2: polish**
15. Second pattern (`grounding_check`).
16. Standalone static single-file HTML report export.

Suggested schedule: **D1** items 1–2; **D2–3** 3–5; **D4** 6–7 and start the backtest; **D5** finish the backtest, tune thresholds, 9; **D6** 10–14 (including Next.js frontend); **D7** article + video; **D8** buffer and submit early.

---

## 13. Evaluation methodology (for the backtest)

- **Data:** choose a public repo with 150–200 closed issues/PRs and consistent maintainer labels or outcomes. Cache the raw JSON locally so the run is reproducible and offline.
- **Proxy labels:** map maintainer outcomes to our categories (e.g., labeled `duplicate`/`question`/`invalid`/`wontfix`, closed-not-planned, merged). These are noisy. **Hand-label a ~60-item gold subset** and report both proxy and gold results.
- **Metrics:** accuracy per band, coverage, escalation rate, false-reject rate on items the maintainers accepted, seconds per item, Bedrock tokens and cost vs baseline.
- **Baseline:** the same items classified by a small Bedrock model on every item (cost and latency measured, accuracy reported).
- **Honest reporting:** include failure cases. A section called "Where it was wrong, and what the confidence said" is valuable for the article.
- Use only public data. Do not post anywhere. Anonymize or omit usernames in published examples.

---

## 14. Sources to read before coding

- Strands Decider repo: `github.com/strands-labs/strands-decider`: README, `docs/architecture.md`, `docs/inference.md`, and **`examples/strands/`** (the `before_tool_call` intervention example).
- Hugging Face model card: `StrandsAgents/strands-decider-2B-hobson-v21`.
- PyPI: `strands-decider`.
- Strands Agents SDK docs: intervention handlers, Bedrock model provider, tool definitions.
- Amazon Bedrock Runtime docs: invoking models, enabling model access, region availability.
- LiteLLM `/v1/systemone` docs describe the HTTP request shape for a self-hosted Decider endpoint (useful reference if you use `serve`).

---

## 15. Questions to ask the user before starting

1. CPU model, core count, and RAM (to size state length and the backtest).
2. Which AWS region, and is Bedrock model access already enabled (and for which small model)?
3. Which public repo should the backtest use? (Offer 2–3 candidates that meet the criteria in section 13.)
4. Is there a sandbox GitHub repo the demo may write to in `--live` mode?
5. Preferred license: MIT or Apache-2.0.

---

## 16. Acceptance criteria (definition of done)

- [ ] `pip install -r requirements.txt && slopgate demo` runs end-to-end on a CPU-only machine in dry-run with no GPU and no paid services.
- [ ] Decider 2B is used for real decisions (Q1 plus at least two noul follow-ups), loaded once, with per-question latency recorded.
- [ ] A Strands agent routes tool calls through `ConfidenceBandHandler`, which returns Proceed/Confirm/Guide/Deny per `policy.yaml`.
- [ ] `close_item` can never execute without explicit maintainer approval, with a unit test proving it.
- [ ] Bedrock is called only for drafts and escalations, within the budget guard, with token counts logged.
- [ ] Every processed item has a receipt (JSON + Markdown).
- [ ] The backtest script reproduces the calibration report from cached data and prints machine specs.
- [ ] `patterns/confidence_band_handler/` is self-contained with README, example, and tests, and is clearly labeled as the reusable Decider 2B decision pattern.
- [ ] The repo has an OSI license, a README with architecture, quickstart, and honest limitations, and contains no secrets.
- [ ] All reported numbers in the README come from scripts in the repo.

---

## 17. Deliverables the user needs for submission (help prepare them)

1. **Public repo** (with the pattern clearly labeled).
2. **Builder Center article** (draft it as `ARTICLE.md`) covering: the problem, the decision handed to Decider and why, the confidence-band design, what Bedrock does, backtest results on ordinary CPU hardware, failures and lessons, and how to reuse the pattern. Tags: `#strands-decider-2b` `#policy`.
3. **Video script** (`VIDEO_SCRIPT.md`), ≤ 2:45, e.g.: 0:00 problem, 0:20 the queue filling with items, 0:45 one item with receipt (high confidence, auto-handled), 1:15 one ambiguous item (low confidence, escalates, maintainer confirms), 1:50 the reusable handler in ~10 lines of config, 2:15 calibration chart, 2:35 close. Label any sped-up segments honestly. No third-party logos or copyrighted music.

---

## 18. Known risks and how to handle them

| Risk | Mitigation |
|---|---|
| CPU too slow | State cap, cascade, caching, background queue, reduced backtest size. |
| Model accuracy modest (~72% general benchmark) | The design assumes this; gating and honest reporting are the story. Measure on our task, not benchmarks. |
| Question wording sensitivity | Test variants; keep the obvious reading; document the winners in the pattern README. |
| False rejection of legitimate newcomers | Nothing is auto-closed; low-effort path is a soft label plus a kind reply; author history excluded by default; report false-reject rate. |
| Unverified APIs (new SDK/model) | Read the example first; smoke-test each integration on day 1. |
| Bedrock cost/quota | Budget guard, templates for common cases, small model, caps. |
| "Not previously published" rule | Keep repo private until submission. |
| Proxy-label noise | Hand-label a gold subset and report both. |

---

*End of brief. Start with section 15 (ask the user), then section 12 item 1 (smoke test), and report back before building further.*
