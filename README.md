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

## Configuration (`.env`)

Copy `.env.example` to create your local `.env`:
```powershell
Copy-Item .env.example .env
```

### 1. Amazon Bedrock Settings
- **`AWS_REGION`**: Set to `us-east-1` (or your chosen Bedrock region).
- **`BEDROCK_MODEL_ID`**: Default is `amazon.nova-micro-v1:0` (free-tier / credit-friendly at ~$0.035 / 1M input tokens).
- **`AWS_ACCESS_KEY_ID` & `AWS_SECRET_ACCESS_KEY`**: Your IAM user access credentials (`AKIA...`).
- **`AWS_SESSION_TOKEN`**: **Leave empty** when using permanent IAM user keys. Only used for temporary credentials (AWS STS or SSO).
- **`AWS_BEARER_TOKEN_BEDROCK`**: **Leave empty** when using IAM access keys. Supplying both bearer token and IAM keys will disrupt SigV4 request signing.

> **New AWS Account Notice:** If you test in the Bedrock playground or API and receive `ValidationException: Operation not allowed`, your new AWS account is undergoing automated background security verification. This normally resolves automatically within 1 to 2 hours.

### 2. GitHub Tokens & Sandbox Setup
- **`GITHUB_TOKEN`**: Personal Access Token (classic or fine-grained) for reading public repositories (such as `pallets/flask`). Bumps GitHub API rate limits from 60 to 5,000 requests/hour. Read-only permissions are sufficient.
- **`GITHUB_WRITE_TOKEN`**: Only required when performing live triage on your own demo repository (`issues:write` and `pull_requests:write`). Leave empty otherwise.
- **`GITHUB_SANDBOX_REPO`**: Your dedicated test repository in `owner/repository` format (e.g. `Niklaus2003/slopgate-sandbox`). Do **not** use `https://...` or `.git` URLs.

### 3. Safety & Budget Controls
- **`SLOPGATE_DRY_RUN=1`**: Simulates all triage actions, label applications, and replies locally without modifying GitHub. Set to `0` only for explicit live sandbox tests.
- **`SLOPGATE_MAX_BEDROCK_CALLS=50`**: Built-in budget guard capping the number of Bedrock calls per run.
- **`SLOPGATE_DECIDER_THREADS=4`**: Recommended CPU thread limit for in-process inference to maintain optimal performance on hybrid CPU architectures.

---

## License
[MIT](LICENSE)

