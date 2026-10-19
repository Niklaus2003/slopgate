# Reusable Decision Pattern: ConfidenceBandHandler

> **Tags:** `#strands-decider-2b` · `#policy`  
> **Status:** Production-ready standalone package. Zero application dependencies.

A reusable, framework-agnostic decision-gating pattern for autonomous AI agents. It intercepts proposed tool calls and evaluates them against the probability outputs of a small local decision model (**Strands Decider 2B**) using mathematically calibrated confidence bands.

```
                      ┌────────────────────────────────────────┐
                      │              AI Agent                  │
                      │       (Strands / Any Framework)        │
                      └──────────────────┬─────────────────────┘
                                         │ Proposes Tool Call
                                         ▼
                      ┌────────────────────────────────────────┐
                      │        ConfidenceBandHandler           │
                      │         (InterventionHandler)          │
                      └──────────────────┬─────────────────────┘
                                         │ Evaluates Gate
                                         ▼
                      ┌────────────────────────────────────────┐
                      │           ConfidenceGate               │
                      │  (Decider 2B Probs → Calibrated Bands) │
                      └──────────────────┬─────────────────────┘
                                         │
                 ┌───────────────┬───────┴───────┬───────────────┐
                 ▼               ▼               ▼               ▼
            [ PROCEED ]     [ CONFIRM ]      [ GUIDE ]       [ DENY ]
           Auto-execute    Human in Loop    Escalate/Hint   Block Tool
```

---

## 🍳 The Recipe Card

### 1. Ingredients
- **Decider Model:** `StrandsAgents/strands-decider-2B-hobson-v21` (or any calibrated multi-class probability classifier).
- **Intervention Layer:** `ConfidenceBandHandler` (adapter extending Strands Agents `InterventionHandler`).
- **Policy Engine:** `ConfidenceGate` with mathematical band normalization and safety invariants.
- **Runtime Cost:** $0.00 compute cost on standard CPU (runs in ~5ms per decision).

---

### 2. Typed Questions & Option Sets

To use this pattern, formulate your domain decisions as typed questions with clear, mutually exclusive options. The Strands Decider evaluates these in a single forward pass over the agent's bounded context.

#### A. Categorical Choice Formulation (e.g. Action Intent)
```python
# Question Text: Concise, canonical prompt (<= 20 words)
QUESTION_TEXT = "What is the primary customer intent of this message?"

# Option Set: 3 to 7 discrete, mutually exclusive targets
OPTIONS = [
    "request_invoice",     # Routine -> Proceed eligible
    "account_inquiry",     # Informational -> Proceed eligible
    "dispute_charge",      # Sensitive -> Escalate / Confirm
    "delete_account",      # Destructive -> Hardcoded Confirm
    "unclear_or_spam",     # Ambiguous -> Guide / Deny
]
```

#### B. Binary Noul Formulation (e.g. Authorization or Grounding)
```python
# Binary question evaluated to True or False
NOUL_QUESTION = "Does the customer's message explicitly request sending an email?"
# Evaluates P(True) vs P(False)
```

---

### 3. Mathematical Threshold Guidance & Calibration

Raw maximum probability $p_{\max}$ is deceptive. On a 5-class choice question, random guessing gives $p_{\max} = 0.20$, whereas on a 2-class question, random guessing gives $p_{\max} = 0.50$.

`bands.py` normalizes raw probability across $N$ options so that **uniform guessing equals 0.0** and **absolute certainty equals 1.0**:

$$\text{Confidence} = \frac{N \cdot p_{\max} - 1}{N - 1}$$

| Band | Threshold Range | Meaning | Safe Routing |
|:---|:---:|:---|:---|
| **`HIGH`** | $\ge 0.80$ | Prediction is clear and unambiguous. | **`PROCEED`** (Auto-execute safe routine tools) |
| **`MEDIUM`** | $0.50 \le \text{conf} < 0.80$ | Plausible prediction, but non-trivial ambiguity. | **`CONFIRM`** (Route to human approval queue) |
| **`LOW`** | $< 0.50$ | Model is guessing near the uniform floor. | **`GUIDE` / `DENY`** (Intervene or steer agent) |

#### Binary Noul Cutoffs:
- **`HIGH (True)`**: $P(\text{True}) \ge 0.85$
- **`HIGH (False)`**: $P(\text{True}) \le 0.15$
- **`LOW / UNCERTAIN`**: $0.15 < P(\text{True}) < 0.85$ (requires human confirmation)

---

### 4. Low-Confidence Behavior (Guide vs Confirm vs Deny)

When confidence drops below the High threshold, `ConfidenceBandHandler` prevents uncalibrated automated tool execution through three distinct mechanisms:

1. **`Confirm(prompt, reason)`**: Used when the tool call is potentially valid but requires human oversight. Suspends automated execution and surfaces a confirmation prompt to a human reviewer.
2. **`Guide(feedback, reason)`**: Used when an agent makes an uncalibrated tool call. Feeds actionable advice back into the agent context, prompting the model to ask the user for clarification instead of guessing.
3. **`Deny(reason)`**: Used when an action violates policy or lacks prerequisite classification. Completely aborts the tool call.

---

### 5. Hardcoded Safety Invariants

Certain operations carry catastrophic risk if executed in error (e.g. deleting databases, purging user accounts, closing open-source issues, issuing unlimited refunds).

`ConfidenceGate` enforces hardcoded safety invariants in code that **cannot be overridden by model confidence**:
- **Destructive Operations Always Confirm:** Any tool matching `delete_*`, `drop_*`, `wipe_*`, `close_*`, or listed in `destructive_tools` returns `CONFIRM`, even if the model is 99% confident.
- **Unlisted Tools Default to Confirm:** Any tool call proposed by an LLM that was not explicitly declared in policy defaults to `CONFIRM`.

---

## 🚀 5-Minute Quickstart (Standalone Usage)

No agent framework required. You can use the gate directly in any Python workflow:

```python
from bands import compute_choice_confidence, classify_choice_band
from gate import ConfidenceGate, DeciderResult, SimplePolicy, ToolPolicy

# 1. Configure policy
policy = SimplePolicy(
    high_at_least=0.80,
    medium_at_least=0.50,
    tools_gated={
        "send_email": ToolPolicy(requires=["intent"]),
        "delete_record": ToolPolicy(always="confirm"),
    },
    routing={
        "send_receipt": {"high": "proceed", "medium": "confirm", "low": "deny"},
    },
)

# 2. Instantiate gate
gate = ConfidenceGate(policy=policy)

# 3. Supply Decider results
decisions = [
    DeciderResult(
        question_id="intent",
        qtype="choice",
        answer="send_receipt",
        probs={"send_receipt": 0.95, "other": 0.05},
        confidence=0.90,
    )
]

# 4. Evaluate tool call
verdict = gate.evaluate(tool_name="send_email", decisions=decisions)
print(f"Action: {verdict.action.value}")  # 'proceed'
print(f"Band:   {verdict.band.value}")    # 'high'
```

---

## 🤖 Strands Agents SDK Integration

Attach the handler to your Strands agent using the standard `InterventionHandler` interface:

```python
from strands import Agent, tool
from handler import AgentContext, ConfidenceBandHandler
from gate import ConfidenceGate, DeciderResult, SimplePolicy, ToolPolicy

# 1. Define tools
@tool
def send_email(recipient: str, subject: str, body: str) -> str:
    """Send an automated customer email."""
    return f"Email sent to {recipient}"

# 2. Per-invocation context provider
current_ctx = AgentContext(
    identifier="ticket#482",
    results=[
        DeciderResult(
            question_id="email_intent",
            qtype="choice",
            answer="send_receipt",
            probs={"send_receipt": 0.96, "other": 0.04},
            confidence=0.92,
        )
    ]
)

# 3. Attach handler to agent
gate = ConfidenceGate()
handler = ConfidenceBandHandler(
    gate=gate,
    context_provider=lambda: current_ctx,
)

agent = Agent(
    model="amazon.nova-micro-v1:0",
    tools=[send_email],
    interventions=[handler],
)
```

---

## 🏢 Non-SlopGate Enterprise Example: Customer Support & CRM

To prove reusability outside of GitHub issue/PR triage, we provide a complete, runnable enterprise CRM support example in [`example_non_slopgate.py`](example_non_slopgate.py).

It demonstrates gating automated customer emails (`send_email`) and user account deletions (`delete_record`):

```bash
python patterns/confidence_band_handler/example_non_slopgate.py
```

### Output:
```text
======================================================================
  Enterprise Support Agent — ConfidenceBandHandler Gating Demo
======================================================================

[Scenario 1] High-Confidence Routine Request
  User Input:   'Please email me my March invoice receipt.'
  Tool Proposed: send_email()
  Gate Verdict:  Proceed
  Audit Rationale: Decider classification 'request_invoice' with confidence 0.91 (band: high) routes to proceed.
  ==> Auto-executed safely without bothering human agents.

[Scenario 2] Ambiguous / Low-Confidence Inquiry
  User Input:   'I might want to close or change something, not sure...'
  Tool Proposed: send_email()
  Gate Verdict:  Guide
  Guidance Sent: Policy guidance for tool 'send_email': Decider classification 'unclear_inquiry' with confidence 0.10 (band: low) routes to guide.
  ==> Gated! Prevented agent from sending unintended emails; guided to ask user.

[Scenario 3] Destructive Action (Hardcoded Safety Invariant)
  User Input:   'Delete my user account and records permanently under GDPR.'
  Tool Proposed: delete_record()
  Gate Verdict:  Confirm
  Prompt to Human: Human confirmation required for tool 'delete_record': Action 'delete_record' is destructive and requires human confirmation.
  ==> Safety Invariant Preserved: Destructive operations NEVER auto-proceed, even at 99% confidence.
```

---

## 🧪 Verification & Testing

The pattern includes its own self-contained test suite with zero application dependencies:

```bash
# 1. Run pattern unit tests
pytest patterns/confidence_band_handler/tests/test_pattern.py -v

# 2. Run the SlopGate example
python patterns/confidence_band_handler/example_agent.py

# 3. Run the non-SlopGate enterprise example
python patterns/confidence_band_handler/example_non_slopgate.py
```

### Self-Containment Guarantee
This folder contains **zero imports** from `src/slopgate/`. It can be copied directly into any Python repository with only `strands-agents` and `pyyaml` (see [`requirements.txt`](requirements.txt)). Verified via AST parsing in `tests/test_pattern_isolation.py`.
