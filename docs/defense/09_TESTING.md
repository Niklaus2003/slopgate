# TESTING: SlopGate Verification Checklist & Test Procedures

> **Concrete Test Commands, Pass Criteria, and Verification Gate.**
> Answers: *"How do we know this works, and where does it fail?"*
> Follows: *Defend What You Ship v2 (Section 02, Habit 8 & Checklist)*

---

## 1. Automated Test Suite

### Running Unit Tests
```powershell
.\.venv\Scripts\python.exe -m pytest -v
```
- **Expected Pass Criteria:**
  - All test functions exit with code `0`.
  - Zero test failures, zero errors.
  - Output ends with `== X passed in Y.YYs ==`.

### Running Code Quality & Linting
```powershell
.\.venv\Scripts\python.exe -m ruff check src tests
```
- **Expected Pass Criteria:**
  - Zero syntax or import errors.
  - Output prints `All checks passed!`.

### Running System Diagnostics
```powershell
.\.venv\Scripts\python.exe -m slopgate.cli doctor
```
- **Expected Pass Criteria:**
  - Virtual environment confirmed active.
  - CPU PyTorch version displayed (`2.14.1+cpu`).
  - Core dependencies marked `[OK]`.
  - AWS and GitHub tokens properly read.

---

## 2. Real Output Verification (Do NOT accept "tests pass" without output)

When validating any change or phase, the developer or AI must record actual terminal execution output:

### Example Verified Output Log:
```text
PS C:\Users\AaronFrancis\Desktop\vscode\research\aws_hackathon> .\.venv\Scripts\python.exe -m pytest -q
..                                                                       [100%]
2 passed in 0.82s
```

---

## 3. End-to-End Manual Path Walk

Before declaring any phase or release complete, perform this manual sanity walk:

1. **Verify Environment Isolation:**
   ```powershell
   .\.venv\Scripts\python.exe -c "import sys; print(sys.executable)"
   ```
   *Must point to `.venv\Scripts\python.exe`.*

2. **Verify CPU PyTorch Execution:**
   ```powershell
   .\.venv\Scripts\python.exe -c "import torch; print('CUDA available:', torch.cuda.is_available()); print('Threads:', torch.get_num_threads())"
   ```
   *Must output `CUDA available: False` and `Threads: 4`.*

3. **Verify GitHub Rate Limit Check:**
   ```powershell
   .\.venv\Scripts\python.exe -c "
   import os, httpx
   from dotenv import load_dotenv
   load_dotenv()
   token = os.getenv('GITHUB_TOKEN')
   r = httpx.get('https://api.github.com/rate_limit', headers={'Authorization': f'Bearer {token}'})
   print('Rate Limit Remaining:', r.json()['rate']['remaining'])
   "
   ```
   *Must show remaining rate limit >= 4900.*

4. **Verify Zero Auto-Close Invariant:**
   Unit test `test_policy_never_auto_closes()` must explicitly assert that passing a `close_item` plan through `ConfidenceGate` always outputs `ActionKind.CONFIRM`, never `ActionKind.PROCEED`.

---

## 4. The Pre-Ship Gate Checklist (Habit 22)

Run this gate before shipping or tagging any phase:

- [x] I can explain how this works at a high level, without notes.
- [x] `DEFENSE.md` is written and current.
- [x] I know why we chose this approach over at least one alternative (`ALTERNATIVES.md`).
- [x] I can name who could abuse it and what stops them (`THREAT.md`).
- [x] I know the first place it will fail and how I would notice (`FAILURE.md`).
- [x] I know the main data structures and why they fit (`DATA.md`).
- [x] I read the full diff, not just an AI summary (`git diff`).
- [x] Tests ran and real output was verified.
- [x] A manual path was executed end-to-end.
- [x] No secrets, keys, or `.env` contents landed in Git history.
- [x] New dependencies are justified and logged (`DEPENDENCIES_AND_SECRETS.md`).
- [x] Rollback steps are written and last good commit is known (`ROLLBACK.md`).
- [x] Unverified assumptions are cleared (`ASSUMPTIONS.md`).
- [x] `HANDOVER.md` and `DECISIONS.md` are updated.
