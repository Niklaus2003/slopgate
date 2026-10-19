# ROLLBACK: SlopGate Rollback & Safe Reversal Procedures

> **Procedures for Safely Reverting Changes and Restoring Service.**
> Answers: *"How do you undo your last change safely?"*
> Follows: *Defend What You Ship v2 (Section 02, Habit 9 & Section 06, Habit 23)*

---

## 1. Checkpoint Log & Known Good States

| Milestone / Phase | Git Commit Hash | Verified Functionality | Safe Reversal Target |
| :--- | :--- | :--- | :--- |
| **Phase 0 Baseline** | `2253a09` | Repo scaffolding, docs, requirements, LICENSE | Revert here if package architecture needs total overhaul. |
| **Phase 1 Initial Build** | `6726835` | CPU PyTorch, venv, doctor command, tests pass | Revert here if core dependencies or build tools break. |
| **Phase 1 Config & Docs Polish** | `3b33b62` | `.env.example`, `README.md`, botocore token sanitization | **Current Last Known Good Commit** on `master`. |

---

## 2. Reversal Workflows

### A. Reverting an Uncommitted or Broken Code Edit
If a new file modification breaks tests or corrupts behavior:
```powershell
# 1. Discard working tree changes to tracked files
git restore .

# 2. Clean any untracked garbage files (except ignored ones)
git clean -fd

# 3. Verify tests pass against last clean commit
.\.venv\Scripts\python.exe -m pytest -q
```

### B. Rolling Back a Committed Phase
If a committed phase needs to be completely undone:
```powershell
# 1. Inspect recent commits
git log --oneline -n 5

# 2. Revert the specific bad commit non-destructively
git revert <bad_commit_hash>

# 3. Or hard reset to the last known good commit (local repo only)
git reset --hard 3b33b62
```

### C. Database State Rollback (`slopgate.db`)
SQLite does not require external migration rollbacks during local development:
```powershell
# To reset database state without losing code:
# Simply delete the local database file; it will auto-recreate on next run
Remove-Item data/slopgate.db* -Force
```

---

## 3. Runtime Emergency Switches (Feature Flags)

If live execution behaves unexpectedly, use these environment variables to immediately neuter side effects without redeploying code:

1. **Disable All GitHub Mutations (Instant Dry-Run):**
   ```env
   SLOPGATE_DRY_RUN=1
   ```
   *Effect:* All actions are printed to stdout or written to receipts as simulated actions; zero GitHub API mutation calls (`POST`, `PATCH`, `DELETE`) are executed.

2. **Disable Bedrock Cloud Invocations:**
   ```env
   SLOPGATE_MAX_BEDROCK_CALLS=0
   ```
   *Effect:* Forces the system into 100% offline mode. Ambiguous items receive standard templated advice; zero tokens or cloud API calls are made to AWS Bedrock.

3. **Fallback to Mock Decider Engine:**
   Run CLI with `--mock` flag or set:
   ```env
   SLOPGATE_DECIDER_MOCK=1
   ```
   *Effect:* Bypasses local PyTorch neural forward pass and uses deterministic mock decision rules for testing.
