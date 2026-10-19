# Defending Open Source from AI Slop Without Alienating Contributors

**Tags:** `#strands-decider-2b` `#policy`

Open-source maintainers face a growing deluge of "AI slop": plausible-sounding but broken pull requests and bug reports. Naive bots that auto-close issues cause severe community backlash by mistakenly rejecting legitimate developers. In open source, **a false rejection is 10x more harmful than letting a low-effort issue sit open.**

We built **SlopGate**: a local-first, confidence-gated triage assistant pairing **Strands Decider 2B** with **Amazon Bedrock** to achieve sub-10ms routine triage, 0.0% false rejections, and zero unattended community closures.

📺 **Walkthrough Demo (94s):** https://youtu.be/arvDCS77caM  
🐙 **GitHub Repository:** https://github.com/Niklaus2003/slopgate  
🧩 **Reusable Pattern:** https://github.com/Niklaus2003/slopgate/tree/main/patterns/confidence_band_handler  

---

### 1. Dual-Model Architecture: Small on CPU, Large in the Cloud
- **Strands Decider 2B (Pure CPU):** Evaluates a bounded 450-token state and deterministic AST facts (paths, syntax trees, repro tracebacks) locally in **5.00 ms on CPU** at **$0.00 compute cost**.
- **Amazon Bedrock (amazon.nova-micro-v1:0):** Reserved exclusively for ambiguous edge cases to draft warm, constructive guidance explaining what traceback or repro steps maintainers need, without accusing contributors of using AI.

---

### 2. The Reusable Decision Pattern: ConfidenceBandHandler (#policy)
Most agents use raw softmax probabilities, which distort confidence across varying option counts. SlopGate normalizes confidence:

$$\text{conf}_{\text{norm}} = \frac{N \cdot p_{\max} - 1}{N - 1}$$

Our standalone package in `patterns/confidence_band_handler/` maps normalized confidence into operational bands:
- **HIGH (>= 0.80):** Unambiguous outcome -> **PROCEED** (auto-applies routine labels).
- **MEDIUM (0.50 - 0.79):** Plausible but uncertain -> **CONFIRM** (diverts to Maintainer Review Queue).
- **LOW (< 0.50):** Uncertain -> **GUIDE / DENY** (triggers Bedrock empathetic draft or blocks tool).

**Hard Safety Invariant:** Destructive actions (`close_item`) **never** auto-proceed, even at 99.9% confidence. Every closure requires human maintainer confirmation.

---

### 3. Empirical Results (50 Pallets/Flask Items)
- **False-Reject Rate on Legitimate Submissions:** **0.0%** (0 false rejections).
- **Unattended Closures:** **0** (100% adherence to safety invariant).
- **Decider 2B Latency (CPU):** **5.00 ms p50** (~90x faster than cloud round-trips).
- **Cost Reduction:** **8.0% to 90% savings** over a 100% cloud LLM baseline.

SlopGate proves agents can be fast, free on CPU, and mathematically safe without alienating contributors.
