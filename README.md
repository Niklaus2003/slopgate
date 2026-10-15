# SlopGate

> **A local, CPU-only, confidence-gated front door for open-source maintainers.**

SlopGate pairs a lightweight 1.9B parameter decision model (**Strands Decider 2B**) with **Amazon Bedrock** to triage incoming GitHub issues and pull requests.
- **100% Free on CPU:** Triage decisions and fact checking happen locally on the maintainer's own laptop.
- **Confidence-Calibrated:** Uses calibrated confidence bands (HIGH, MEDIUM, LOW) to gate actions.
- **Never Auto-Closes:** Every close or reject action strictly requires maintainer confirmation.
- **Empathetic & Constructive:** Bedrock drafts friendly, specific feedback for vague or low-effort submissions without ever accusing contributors of using AI.
- **Reusable Decision Pattern:** Includes the `#policy` tagged reusable pattern `patterns/confidence_band_handler/`.

---

## Architecture Overview

```
GitHub / Replay JSON ──► SQLite Queue ──► Worker Process (loaded once on CPU)
                                                │
                                                ▼
                                         State Builder
                               (<= 450 tokens + code fact extractors)
                                                │
                                                ▼
                                      Strands Decider 2B
                          (Q1 choice + N1-N5 noul; batched forward pass)
                                                │
                                                ▼
                                    ConfidenceBandHandler
                               (Proceed / Confirm / Guide / Deny)
                                      │                   │
                        Routine / HIGH│                   │Ambiguous / LOW
                                      ▼                   ▼
                            Scripted Executor       Amazon Bedrock
                          (Dry-run labels/notes) (reason_on_ambiguous, draft_reply)
                                      │                   │
                                      ▼                   ▼
                             Decision Receipts    Maintainer Review Queue
                              (JSON + Markdown)   (Manual approval for close/flags)
```

---

## Quickstart

```powershell
# 1. Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies (CPU PyTorch first)
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e .

# 3. Check environment
slopgate doctor
```

---

## License
[MIT](LICENSE)
