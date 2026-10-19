S TOP C L I CK I NG A L LOW

## DEFEND WHAT YOU SHIP.

V2

WHITEBOARD

25 habits for using AI without losing the plot, and the one test that keeps you honest.

A F I ELD GU I DE FOR PEOPLE WHO BU I LD WI TH A I

EDITION

Every allow click is a decision. This guide gives you the paper trail, the guardrails and the benchmark to make it an informed one.


0 0 / THE PROBLEM

## FAST IS EASY. OWNING IT IS HARD.

AI coding assistants move quickly. They propose a change, you hit allow, and the context behind it, the reasoning, the tradeoffs and the files it touched, disappears when the session ends.

Next session the AI starts from zero. So do you. Bugs get harder to trace, the why behind every decision is lost and you are no longer directing the work. You are approving it.

The fix is not slowing down. It is writing things down, and being able to explain what you ship.

## HOW TO USE TH I S GU I DE

Start with the Whiteboard Defense benchmark on the next pages. It is the goal. The 25 habits that follow are the tools. The cheat sheets, checklist and templates at the back are for copying straight into your project.


THE BENCHMARK

## THE WHITEBOARD DEFENSE

“

I should be able to pull you aside at any moment and ask you to explain any customer facing system you have shipped. You should be able to clearly explain how it works and defend the decisions you made.

TH I S I S THE BENCHMARK FOR RESPONS I BLE A I USAGE

## WHAT IS NOT EXPECTED

- Line level familiarity with the code.

- Remembering exact function names.

- Recalling implementation details. You may not even know them, and that is fine.

## WHAT IS EXPECTED

- A clear, confident, high level explanation of how it works.

- The ability to defend the decisions behind it.

- Honest answers about where it breaks and how it could be abused.

Understanding is not memorization. It is knowing why the system looks the way it does, and what happens when it is pushed.

DEFEND WHAT YOU SHIP / AI COLLABORATION FIELD GUIDE v2


THE FOUR QUEST I ONS

## BE READY FOR THESE

## 1. "Why did you do X instead of Y?"

## A GOOD ANSWER INCLUDES

The options you considered, what each would have cost, and the specific reason this one won for this situation.

## RED FLAG

"The AI suggested it." That is a source, not a reason.

BACK I T UP WI TH

Decisions.md, Alternatives.md

## 2. "What happens if this actor behaves maliciously?"

## A GOOD ANSWER INCLUDES

Who the actors are, what they can reach, what they could send or abuse, and which controls stop them (validation, auth checks, rate limits, least privilege).

## RED FLAG

"Users would not do that." They will.

## BACK I T UP WI TH

Threat.md, Constraints.md, Architecture.md

## 3. "What data structure did you use here and why?"

## A GOOD ANSWER INCLUDES

The shape of the data, how it is read and written, how large it can get, and the trade-off the structure makes.

## RED FLAG

Not knowing the structure exists, or why it suits the access pattern.

## BACK I T UP WI TH

Data.md, Flow.md

## 4. "Where does this fail?"

## A GOOD ANSWER INCLUDES

The first limit you expect to hit, what happens when a dependency is down or slow, and how you would notice.

## RED FLAG

"It should not fail." Every system fails somewhere.

## BACK I T UP WI TH

Failure.md, Test checklist, Rollback.md

DEFEND WHAT YOU SHIP / AI COLLABORATION FIELD GUIDE v2


## TWO LANES

## KNOW WHICH LANE YOU ARE IN

The defense standard does not apply to everything. It applies to what customers touch.

|   | LANE A: POC, DEMO, | LANE B: CUSTOMER FACING |
| --- | --- | --- |
|   | EXPERIMENT |   |
| GOAL | Learn fast. Test an idea. Throw it | Serve real people reliably and safely. |
|   | away if it fails. |   |
| AI USAGE | Generate 100% of it. | Use AI heavily, but stay the author of the |
|   |   | decisions. |
| UNDERSTANDING | Understand none of it. That is fine. | Understand it at a high level. Defensible at |
|   |   | a whiteboard. |
| PRIORITY | Speed over quality, every time. | Correctness, safety and clarity over raw |
|   |   | speed. |
| DOCS | None needed. | Core files, Defense.md and the pre ship |
|   |   | gate. |
| IF IT BREAKS | Nobody is harmed. Delete it. | Customers, data or money are affected. |

## THE PROMOT I ON RULE

The moment a PoC gets a real user, it moves to Lane B. Any code you generated and never understood now needs its defense written before it stays live.

## QU I CK TEST

Ask: if this broke tonight, would a customer notice or be harmed? If yes, you are in Lane B. If no, generate freely and move fast.


## S EC T I ON 0 1

The backbone of any serious AI assisted workflow. Keep these next to your code, not just in your head.

## THE CORE FIVE

## 1 HANDOVER FILES

Write context incrementally in a file the AI reads at the start of every session. Not a dump of everything. A living record of where things stand right now: what is done, what is in progress, what is broken and what to avoid.

CONTINUITY

## HOW TO DO I T

- Keep one HANDOVER.md in the repo and add the newest entry on top.

- Use fixed sections: Done, In progress, Broken, Next, Do not touch.

- Tell the AI to read it first and update it last, every single session.

WHY I T MATTERS Every new AI session starts with amnesia. A handover file is the difference between re- explaining the whole project and picking up exactly where you left off.

## 2 DECISIONS.MD

## ANSWERS: WHY X INSTEAD OF Y?

Log every meaningful decision the AI makes while changing your code, together with the reasoning. Why this library over that one, why this pattern, why this tradeoff was accepted.

RATIONALE

## HOW TO DO I T

- One entry per decision: context, options, choice, reason, date.

- Ask the AI to draft the entry before it makes the change, not after.

- Record the rejected options too. They are the best part of the log.

WHY I T MATTERS Code shows what changed. Decisions.md shows why. Six months later that why is the only thing that stops you re-arguing settled questions.


## 3 EXPLICIT COMMENTS

Require the AI to comment non obvious logic as it writes it. Not restating the code, but explaining the flow: what this block is for, what calls into it and what it assumes.

READABILITY

## HOW TO DO I T

- Comment intent and assumptions, never syntax.

- Mark invariants, for example: must run after auth check.

- Flag surprising code with a WHY note so nobody cleans it up later.

WHY I T MATTERS Comments are cheap insurance. They let you, or the next AI session, understand intent without reverse engineering it.

## 4 FLOW.MD

TRACEABILITY

## ANSWERS: WHERE DOES THIS FAIL?

Document how execution actually travels between files, functions and modules. What calls what, in what order, and exactly which part of that path you are changing right now.

## HOW TO DO I T

- Trace from entry point to output: file, function, next file, next function.

- Mark the exact functions or lines being modified in this change.

- Update it whenever the path changes. A plain text diagram is enough.

WHY I T MATTERS Bugs live in the gaps between files. If you cannot see the flow you cannot see where it breaks, and neither can the AI.

## 5 BUG.MD / FEATURE.MD

Keep one file per bug or feature that traces it from beginning to end: how it was found or scoped, what was tried, what worked, what did not, and how it was verified.

FULL TRACE

## HOW TO DO I T

- Bug: symptom, repro steps, root cause, fix, verification.

- Feature: goal, scope, design, steps, status, open questions.

- Append a timestamped log. Never rewrite history.

WHY I T MATTERS Anyone, human or AI, should be able to read this file cold and know exactly how to continue.


## S EC T I ON 0 2

Beyond tracking what happened, these files control what is allowed to happen before the AI touches a line.

## GUARDRAILS

## 6 ARCHITECTURE.MD

BIG PICTURE

## ANSWERS: ALL FOUR QUESTIONS

A high level map of the system: modules, services and how data moves between them. Not implementation detail. The shape of the thing, so the AI does not re-derive it every session.

## HOW TO DO I T

- List each module or service and what it owns.

- Show data flow and mark the trust boundaries (where outside input enters).

- Keep it to one page and link to deeper docs.

WHY I T MATTERS Without a map every session starts by guessing the terrain. With one, the AI can reason about impact before it writes a line.

## 7 CONSTRAINTS.MD

BOUNDARIES

## ANSWERS: WHAT IF AN ACTOR IS MALICIOUS?

A short, explicit list of what the AI must never do: do not touch the payment module, always use the repository pattern, no new dependencies without asking.

## HOW TO DO I T

- Write hard rules in plain words: never, always, only.

- Name protected areas: auth, payments, migrations, infra.

- Instruct the AI to stop and ask before it breaks any rule.

WHY I T MATTERS Allow should never mean allow anything. Constraints turn blanket permission into scoped permission.


## 8 TEST CHECKLIST

VERIFICATION

## ANSWERS: WHERE DOES THIS FAIL?

A concrete list of what to run and check before any change counts as done. Not a vibe check. Actual commands and actual expected outputs.

## HOW TO DO I T

- List exact commands and what a pass looks like.

- Add one manual path that a real customer would take.

- Make the AI paste real output instead of saying tests pass.

WHY I T MATTERS An AI claiming success and code actually working are two different facts. This file is how you stop confusing them.

## 9 ROLLBACK.MD

SAFETY NET

## ANSWERS: WHERE DOES THIS FAIL?

A short plan for undoing a change if it breaks something, especially for large or risky edits. Which commit to return to, which files to restore and what to re check afterwards.

## HOW TO DO I T

- Note the last known good commit or tag before every risky change.

- For data changes, write the down step or the backup plan.

- Prefer a feature flag so you can switch it off without a deploy.

WHY I T MATTERS Confidence to let AI make bigger changes comes from knowing exactly how to reverse them.


## S EC T I ON 0 3

Documents only work if you actually read them. These habits keep a human in the loop.

## REVIEW HABITS

## 10 READ THE DIFF

Never accept a change based on the AI's summary of it. Read the actual diff, every time, no matter how small the request seemed.

DISCIPLINE

## HOW TO DO I T

- Scan the list of changed files first. Did it touch anything unexpected?

- Hunt for deleted tests, loosened checks, hardcoded values and new network calls.

- If the diff is too big to read, the request was too big.

WHY I T MATTERS Summaries can be wrong or incomplete. Diffs cannot lie about what actually changed.

## 11 ASK WHY BEFORE WHAT

## ANSWERS: WHY X INSTEAD OF Y?

Before the AI implements anything, make it explain its plan and approach. Catch bad reasoning while it is still a paragraph, not after it is 200 lines of code.

PLAN FIRST

## HOW TO DO I T

- Prompt: explain your plan and the alternatives before editing anything.

- Ask: what could go wrong with this plan?

- Approve the plan first, then approve the code.

WHY I T MATTERS It is far cheaper to correct a flawed plan than to unwind a flawed implementation.


## 12 SMALL REQUESTS ONLY

One logical change per request. Not fix my whole auth system. Smaller asks are easier to verify and mistakes stay traceable to a single step.

SCOPE CONTROL

## HOW TO DO I T

- One behavior change per prompt.

- Commit between steps so each one can be reverted alone.

- If you cannot name the change in one sentence, split it.

WHY I T MATTERS Large vague requests produce large vague diffs. Nobody reviews those properly, not even the AI.

## S EC T I ON 0 4

The habits that hold the system together, session after session.

## META HABITS

## 13 SESSION HANDOFF SUMMARY

End every session with a five line note: what we did, what is left, what to watch out for. It takes 30 seconds and saves the next session from starting cold.

RITUAL

## HOW TO DO I T

- Last prompt of the day: summarize in 5 lines, done, left, risks.

- Paste the result into HANDOVER.md.

- Do it even when you are tired. Especially then.

WHY I T MATTERS The cheapest habit on this list and often the highest leverage one.


## 14 VERSION PIN YOUR CONTEXT

Note which AI model or version made which decision. Behavior shifts between versions, so knowing who reasoned through a change matters when you debug it later.

TRACEABILITY

## HOW TO DO I T

- Put the model name and date in each Decisions.md entry.

- Log it when you switch models mid project.

- After a model change, re verify old assumptions before building on them.

WHY I T MATTERS The AI did this is not a full answer once you juggle several models across a project's lifetime.

15 OWN THE MENTAL MODEL

THE REAL RULE

## ANSWERS: ALL FOUR QUESTIONS

If you cannot explain what the code does in your own words, you are not ready to accept it, however thorough the documentation. Docs support your understanding. They do not replace it.

## HOW TO DO I T

- Explain the change out loud with no notes.

- Sketch the data flow on paper.

- If you stall, have the AI explain that part, then try again from scratch.

WHY I T MATTERS This is the whole point. Every file here exists to get you to this moment, not to excuse you from it.


S EC T I ON 0 5

## DEFENSE PREP

New in v2. These files exist so you can survive the whiteboard: the four questions a reviewer can ask at any moment.

## 16 DEFENSE.MD

CAPSTONE

## ANSWERS: ALL FOUR QUESTIONS

A one page brief per customer facing system that answers, in your own words: what it does, how it works, why it was built that way, how it can be abused and where it breaks. This is your whiteboard cheat sheet.

## HOW TO DO I T

- Write it after the build and before the ship.

- Draft it yourself first, let the AI fill gaps, then rewrite the result in your voice.

- Re read it before every release that changes the system.

WHY I T MATTERS If you can fill this page without help, you pass the benchmark. If you cannot, you have found the exact gap to close before shipping.

## 17 ALTERNATIVES.MD

TRADE-OFFS

## ANSWERS: WHY X INSTEAD OF Y?

For every significant choice, write down the options you rejected and why. Why a queue and not a cron job. Why Postgres and not a document store. This is the raw material for any why X instead of Y answer.

## HOW TO DO I T

- List two or three real options for each major decision.

- Note cost, risk and what you gave up by choosing.

- Add a revisit if line: the condition that would change your mind.

WHY I T MATTERS Defending a decision is easy when you remember the alternatives. Without them every choice sounds like the only possible one, and that is a red flag.


18 THREAT.MD

SECURITY

## ANSWERS: WHAT IF AN ACTOR IS MALICIOUS?

List who could behave badly and what they could do. An anonymous visitor, a logged in user, an insider, a third party API, a compromised dependency. For each, what can they send, see or break?

## HOW TO DO I T

- List actors and entry points (forms, APIs, webhooks, file uploads).

- For each, write the worst realistic abuse and the mitigation in place.

- Be honest about known gaps. An admitted gap beats a hidden one.

WHY I T MATTERS AI writes code that works for the happy path. Attackers live on every other path. This is how you notice them before a customer does.

## 19 FAILURE.MD

RESILIENCE

## ANSWERS: WHERE DOES THIS FAIL?

A map of how the system fails. Walk each dependency and ask: what if it is slow, down, wrong or empty? Note the limits too: size, scale, concurrency and timeouts.

## HOW TO DO I T

- Go dependency by dependency: database, APIs, queues, third parties.

- Write the first limit you expect to hit (traffic, payload size, rate limit).

- Note how you would find out: logs, alerts, dashboards.

WHY I T MATTERS Where does this fail is the question that separates people who understand a system from people who merely deployed it.


20

DATA.MD

STRUCTURES

## ANSWERS: WHAT DATA STRUCTURE AND WHY?

Record the key data structures and schemas you rely on, how they are accessed, how big they get and who is allowed to write them. Plain words are fine. The point is the reasoning.

## HOW TO DO I T

- For each core structure, note shape, access pattern and expected size.

- State the trade-off in one line, for example fast lookup, costly ordering.

- Record who writes the data and who only reads it.

WHY I T MATTERS What data structure did you use and why is a fair question. The AI picked one. You need to know why it was a good pick.

S EC T I ON 0 6

## SHIP GATE HYGIENE

New in v2. Small habits that keep the allow button from becoming a liability.

## 21 ASSUMPTIONS & OPEN QUESTIONS

HONESTY

## ANSWERS: WHERE DOES THIS FAIL?

Keep a running list of what you and the AI are assuming but have not verified, plus questions nobody has answered yet. Unverified assumptions are where most production bugs are born.

## HOW TO DO I T

- Ask the AI at the end of each task: what did you assume that I did not tell you?

- Mark each item as verified, unverified or wrong.

- Clear the unverified list before anything ships to customers.

WHY I T MATTERS AI fills gaps confidently. Writing the gaps down is how you stop confidence from passing as knowledge.


22 LEAST PRIVILEGE ALLOW POLICY

PERMISSIONS

## ANSWERS: WHAT IF AN ACTOR IS MALICIOUS?

Decide in advance what you will auto allow, what you will pause on and what you will never allow. Do not make that call fresh at every popup while tired and rushing.

## HOW TO DO I T

- Sort actions into three lists: safe, pause and read, never.

- Keep AI tools out of production credentials and live databases.

- Review the allow list when your project or risk level changes.

WHY I T MATTERS Clicking allow is granting access. A written policy makes that grant a deliberate decision. See the cheat sheet later in this guide.

## 23 ONE COMMIT PER AI CHANGE

GIT HYGIENE

## ANSWERS: WHERE DOES THIS FAIL?

Commit after every accepted AI change with a message that says what and why. Your git history becomes a step by step record you can bisect, revert and explain.

## HOW TO DO I T

- Commit before you start a risky prompt so you can return to it.

- Write messages as intent: what changed and why, not just update.

- Never stack five unrelated AI edits into one commit.

WHY I T MATTERS When something breaks next week, small commits turn a mystery into a ten minute bisect.

DEFEND WHAT YOU SHIP / AI COLLABORATION FIELD GUIDE v2


24 DEPENDENCY & SECRETS LOG

SUPPLY CHAIN

## ANSWERS: WHAT IF AN ACTOR IS MALICIOUS?

Track every dependency the AI adds and every secret, key or credential it touches. AI will happily install a package you have never heard of or paste a key into a file.

## HOW TO DO I T

- Record the package, why it is needed and who maintains it.

- Scan diffs for keys, tokens and .env contents before committing.

- Pin versions and prefer fewer, well known libraries.

WHY I T MATTERS Every new dependency is code you did not write and probably will not read. It deserves a reason on file.

25 TEACH BACK DRILL

PRACTICE

## ANSWERS: ALL FOUR QUESTIONS

Practice the whiteboard before anyone asks. Explain your system to a friend, a rubber duck or the AI itself, then have the AI quiz you with the four questions and grade your answers.

## HOW TO DO I T

- Prompt: act as a skeptical reviewer and ask me about this system.

- Answer from memory first, then check against Defense.md.

- Where you stumble, fix the understanding, then the docs.

WHY I T MATTERS Defense is a skill, and skills need reps. The drill is where you find out what you do not understand while it is still cheap.


## ALLOW, PAUSE OR NEVER

Decide this once, calmly, instead of at every popup. Adapt the lists to your project.

## PAUSE AND READ

- Edits across many files

- Config or build changes

- Adding a dependency

- Changing auth or permissions

- Database writes or migrations

- Calls to a new external host

- Deleting files

Rule of thumb: the harder an action is to undo, the less it deserves a fast click.

## RED FLAGS I N A D I FF

|   | YOU SEE Tests deleted or skipped | ASK Why is the safety net shrinking? |   |
| --- | --- | --- | --- |
|   | Validation or auth checks loosened New package or network call Hardcoded values, keys or URLs Huge diff for a small request | Who benefits from this being easier? Do I know what this is and who runs it? Where should this really live? What else changed that I did not ask for? |   |


CHECKL I ST

## THE PRE SHIP GATE

Run this before anything in Lane B goes live. If you cannot tick a box honestly, you are not ready to ship.

I can explain how this works at a high level, without notes.

Defense.md is written in my own words and is current.

I know why we chose this approach over at least one alternative.

I can name who could abuse it and what stops them.

I know the first place it will fail and how I would notice.

I know the main data structures and why they fit.

I read the full diff, not just the AI's summary.

Tests ran and I saw the real output.

A customer path was tried by hand end to end.

No secrets, keys or tokens landed in the code.

New dependencies are justified and logged.

Rollback steps are written and the last good commit is known.

Unverified assumptions are cleared or consciously accepted.

HANDOVER.md and Decisions.md are updated.


COPY AND PASTE

## STARTER TEMPLATES

### 01_HANDOVER.md

```markdown
# HANDOVER
## Latest session: 2026-10-15 (model: name + version)
Done:
- ...
In progress:
- ...
Broken or risky:
- ...
Next:
- ...
Do not touch:
- ...
Read first: docs/defense/02_CONSTRAINTS.md, docs/defense/03_FLOW.md
```

### 02_CONSTRAINTS.md

```markdown
# CONSTRAINTS: System Boundaries & Rules
## Hard System Invariants (NEVER violate)
- 1. ...
- 2. ...
## Protected Code Areas
- ...
## Least Privilege Allow Policy
- Auto-Allow (Safe): reading files, running linters, tests.
- Pause & Confirm: schema migrations, adding dependencies, external calls.
- Never Allow: hardcoding secrets, bypassing safety gates, deleting tests.
```

### 03_FLOW.md

```markdown
# FLOW: Execution Path Map
## End-to-End Diagram
Input -> Step 1 -> Step 2 -> Output
## Call Chain & Trust Boundaries
- Boundary 1: ...
```

### 04_DATA.md

```markdown
# DATA: Core Data Structures & Schemas
## Core Models
- Model Name: Shape, fields, size limits, access pattern, trade-offs.
## Database Schemas
- Table definitions and indexes.
```

### 05_DECISIONS.md (one entry)

```markdown
## D-001: <Title of decision>
Date: 2026-10-15 Model: name + version
Context: ...
Options: 1) ... 2) ... 3) ...
Chosen: 2
Why: ...
Trade-off: ...
Revisit if: ...
```

### 06_ALTERNATIVES.md

```markdown
# ALTERNATIVES: Rejected Options Log
| Decision | Options Considered | Why Rejected | Cost / What We Gave Up | Revisit If |
|---|---|---|---|---|
| Choice 1 | Option A vs Option B | ... | ... | ... |
```

### 07_THREAT.md

```markdown
# THREAT: Threat Model & Security Posture
## Actors & Entry Points
- Actor 1 (Untrusted / Anonymous): entry point, abuse vectors.
## Threat Scenarios & Mitigations
- Threat: ... (Worst realistic impact & mitigation)
```

### 08_FAILURE.md

```markdown
# FAILURE: Resilience & Failure Modes
## Dependency Walk
- Service A: what if slow, down, wrong, empty?
## First Limits We Expect to Hit
- ...
## Observability (How we notice)
- ...
```

### 09_TESTING.md

```markdown
# TESTING: Verification & Pre-Ship Gate
## Automated Commands
- pytest commands and expected output.
## Pre-Ship Gate Checklist
- [ ] Whiteboard defensible without notes.
- [ ] Diffs inspected. Tests verified with real output.
```

### 10_ROLLBACK.md

```markdown
# ROLLBACK: Recovery & Safe Undo
## Known Good Checkpoints
- Commit hash and verified status.
## Emergency Feature Flags
- Flags to disable live mutations or cloud calls.
```

### 11_DEFENSE.md

```markdown
# DEFENSE: <system name>
## What it does (2 sentences):
...
## How it works (sketch the execution flow):
...
## Key decisions and why X over Y:
...
## Data structures and why:
...
## How a malicious actor could abuse it:
...
## Where it fails and how we notice:
...
## What I would change with more time:
...
```

### 12_DEPENDENCIES_AND_SECRETS.md

```markdown
# DEPENDENCIES & SECRETS: Supply Chain Audit
## Dependency Inventory
| Package | Version | License | Maintainer | Justification |
## Secrets Policy
- Secret management and environment variable hygiene rules.
```

### 13_ASSUMPTIONS.md

```markdown
# ASSUMPTIONS: Open Questions Log
| ID | Assumption | Status (VERIFIED / UNVERIFIED) | Evidence |
```



DEFEND WHAT YOU SHIP / AI COLLABORATION FIELD GUIDE v2


GET STARTED

## FOLDER LAYOUT & REUSABLE SETUP: `docs/defense/`

For any new project or product, keep your root directory clean and maintain all defense artifacts together in strict sequential order by creating a `docs/` folder with a numbered `defense/` subfolder:

```text
your-project/
├── docs/
│   ├── defense/                           # <-- Dedicated Sequentially Numbered Defense Folder
│   │   ├── 00_FIELD_GUIDE.md              # Master field guide reference (copy this file alone)
│   │   ├── 01_HANDOVER.md                 # Living record of where things stand (done, in progress, broken, next)
│   │   ├── 02_CONSTRAINTS.md              # Hard boundaries, off-limits areas, least privilege allow policy
│   │   ├── 03_FLOW.md                     # Execution path: what calls what from entry to output
│   │   ├── 04_DATA.md                     # Core data structures, shapes, schemas, size caps, access patterns
│   │   ├── 05_DECISIONS.md                # Why X instead of Y? Context, options, choice, reason, trade-offs
│   │   ├── 06_ALTERNATIVES.md             # Options considered and rejected for every major choice
│   │   ├── 07_THREAT.md                   # Threat model: bad actors, worst realistic abuse, mitigations
│   │   ├── 08_FAILURE.md                  # Resilience walk: what if dependencies slow/fail, first limits
│   │   ├── 09_TESTING.md                  # Concrete test commands, pass criteria, and the pre-ship gate
│   │   ├── 10_ROLLBACK.md                 # The way back out: last known good commit, down-steps, feature flags
│   │   ├── 11_DEFENSE.md                  # The Whiteboard Defense Brief: one-page capstone answering the 4 questions
│   │   ├── 12_DEPENDENCIES_AND_SECRETS.md # Supply chain inventory, licenses, and credential hygiene
│   │   ├── 13_ASSUMPTIONS.md              # Living log of verified vs unverified assumptions
│   │   ├── features/                      # Optional: FEATURE-001.md full traces
│   │   └── bugs/                          # Optional: BUG-001.md root cause traces
│   └── ...                                # General project documentation
```

### Quick Setup Steps for Future Projects:
1. **Create the directory:** `mkdir -p docs/defense`
2. **Copy this field guide:** Place `00_FIELD_GUIDE.md` into `docs/defense/`.
3. **Scaffold the numbered files:** Create files `01_` through `13_` using the templates above inside `docs/defense/`.
4. **Instruct your AI assistant:** At the beginning of the project, provide this exact prompt:
   > *"We follow the Defend What You Ship v2 standard located in `docs/defense/00_FIELD_GUIDE.md`. All defense artifacts are stored sequentially in `docs/defense/`. Read `docs/defense/01_HANDOVER.md` and `docs/defense/02_CONSTRAINTS.md` first, draft rationale in `docs/defense/05_DECISIONS.md` before non-trivial changes, and keep every system defensible at a whiteboard."*

- **DAY 1:** Handover & Constraints (`01_HANDOVER.md`, `02_CONSTRAINTS.md`). Tell the AI to read them first.
- **DAY 2:** Flow & Architecture (`03_FLOW.md`). Draw the system map and trace one real request through it.
- **DAY 3:** Data & Decisions (`04_DATA.md`, `05_DECISIONS.md`). Document core structures and start logging choices.
- **DAY 4:** Alternatives (`06_ALTERNATIVES.md`). Record the options you turned down and why.
- **DAY 5:** Threat & Failure (`07_THREAT.md`, `08_FAILURE.md`). Spend an hour being your own attacker, then your outage.
- **DAY 6:** Test & Rollback (`09_TESTING.md`, `10_ROLLBACK.md`). Write the test checklist and note the last good commit.
- **DAY 7:** Whiteboard Capstone (`11_DEFENSE.md`). Run your first whiteboard drill answering the 4 core questions.


SELF TEST

## THE WHITEBOARD DRILL

Pick one customer facing system you shipped. Answer these out loud, with no notes. Where you hesitate, that is your homework.

- 1. What does this system do, in two sentences a new teammate would understand?

- 2. Walk me through one request from entry to response.

- 3. Why did you choose this approach instead of the obvious alternative?

- 4. What is the most important data structure here and why does it fit?

- 5. What is the worst thing an anonymous user could try?

- 6. What about a logged in user who is malicious?

- 7. What happens if your main dependency goes down for an hour?

- 8. What is the first limit you expect to hit as usage grows?

- 9. How would you know it broke before a customer told you?

- 10. How do you undo your last change safely?

- 11. What did the AI assume that you never verified?

- 12. What would you change if you had another week?

Score yourself: 10 or more confident answers means you could ship it. Fewer than that means it is not Lane B ready yet.


## STOP APPROVING. START DIRECTING.

- 01 Handover Files

- 02 Decisions.md

- 03 Explicit Comments

- 04 Flow.md

- 05 Bug.md / Feature.md

- 06 Architecture.md

- 07 Constraints.md

- 08 Test Checklist

- 09 Rollback.md

- 10 Read The Diff

- 11 Ask Why Before What

- 12 Small Requests Only

- 13 Session Handoff Summary

A blind allow is not a decision. This is.

- 14 Version Pin Your Context

- 15 Own The Mental Model

- 16 Defense.md

- 17 Alternatives.md

- 18 Threat.md

- 19 Failure.md

- 20 Data.md

- 21 Assumptions & Open Questions

- 22 Least Privilege Allow Policy

- 23 One Commit Per AI Change

- 24 Dependency & Secrets Log

- 25 Teach Back Drill

For demos and experiments: generate everything, understand nothing, move fast. For anything a customer touches: be ready to defend it at a whiteboard.
