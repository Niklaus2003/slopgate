# DEPENDENCIES & SECRETS: SlopGate Supply Chain & Credential Hygiene

> **Supply Chain Audit and Secret Protection Log.**
> Answers: *"What external code runs in this system, and how are secrets kept safe?"*
> Follows: *Defend What You Ship v2 (Section 06, Habit 24)*

---

## 1. Third-Party Dependency Inventory

Every dependency in this project is explicitly justified, version-pinned, and audited for minimal attack surface:

| Package | Pinned Version | License | Maintainer / Source | Justification & Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **`torch`** | `2.14.1+cpu` | BSD-style | PyTorch Foundation / Meta | Minimal CPU-only tensor runtime for running Strands Decider 2B without CUDA overhead. |
| **`strands-decider`** | `0.1.0` | Apache-2.0 | Strands Agents Team | Core in-process Qwen3.5-2B decision evaluation library for choice & noul questions. |
| **`strands-agents`** | `1.61.0` | Apache-2.0 | Strands Agents Team | Strands agent framework, tool schemas, and native intervention actions (`Proceed`, `Confirm`, etc.). |
| **`boto3`** | `1.43.114` | Apache-2.0 | Amazon Web Services | Official AWS SDK for invoking Amazon Bedrock Nova Micro via the Converse API. |
| **`pydantic`** | `2.14.1` | MIT | Pydantic / Samuel Colvin | Strict schema validation, type parsing, and data sanitization for items, states, and receipts. |
| **`httpx`** | `0.28.1` | BSD-3-Clause | Encode / Tom Christie | Modern async/sync HTTP client for GitHub REST API calls with connection pooling and timeouts. |
| **`scikit-learn`** | `1.9.1` | BSD-3-Clause | scikit-learn developers | Standard calibration curve calculations, Brier score metrics, and expected calibration error (ECE). |
| **`rank-bm25`** | `0.2.2` | Apache-2.0 | Dorian Brown | Fast, zero-dependency BM25 keyword search for finding similar existing issues/PRs in local cache. |
| **`pyyaml`** | `6.0.3` | MIT | YAML Project | Parsing configuration files and test fixtures. |
| **`pytest`** | `9.1.1` | MIT | Holger Krekel et al. | Automated test suite execution, fixtures, and assertions. |
| **`ruff`** | `0.17.0` | MIT | Astral | Ultra-fast Python linter and code quality enforcement. |

---

## 2. Secrets Management & Credential Policy

### Monitored Environment Variables (`.env`)
1. `AWS_ACCESS_KEY_ID`: Standard AWS IAM access key (starts with `AKIA...`).
2. `AWS_SECRET_ACCESS_KEY`: AWS IAM secret key.
3. `AWS_SESSION_TOKEN`: **Must be blank** for permanent IAM keys.
4. `AWS_BEARER_TOKEN_BEDROCK`: **Must be blank** when using IAM keys.
5. `GITHUB_TOKEN`: Read-only GitHub PAT for public repo data ingestion.
6. `GITHUB_WRITE_TOKEN`: Scoped GitHub PAT limited exclusively to `Niklaus2003/slopgate-sandbox`.

### Automated Credential Safeguards
- **`.gitignore` Enforced:** `.env`, `.env.*` (except `.env.example`), `docs/`, and `scripts/` are strictly ignored.
- **Botocore Sanitization:** `src/slopgate/config.py` automatically detects and deletes empty-string AWS environment variables immediately after `load_dotenv()` to prevent breaking SigV4 authentication.
- **No Console Logging of Tokens:** CLI commands and logging formatters mask or omit all authorization headers.
- **Pre-Commit Diffs Scan:** Every diff must be inspected to ensure no hardcoded tokens, secret strings, or user credentials are committed into tracked repository code.
