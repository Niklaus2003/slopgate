# DATA: SlopGate Core Data Structures & Schemas

> **Specification of Key Data Structures, Shapes, and Access Patterns.**
> Answers: *"What data structure did you use here and why?"*
> Follows: *Defend What You Ship v2 (Section 05, Habit 20)*

---

## 1. Core Domain Models (`src/slopgate/models.py`)

### `Item`
- **Purpose:** Represents an incoming GitHub issue or pull request.
- **Shape:**
  ```python
  class Item(BaseModel):
      id: str  # Format: "{repo}#{number}" (e.g., "pallets/flask#5432")
      repo: str
      number: int
      kind: Literal["issue", "pr"]
      title: str
      body: str
      author: str
      created_at: datetime
      diff_text: Optional[str] = None
      labels: List[str] = Field(default_factory=list)
      status: Literal["queued", "processing", "processed", "failed"] = "queued"
  ```
- **Why this structure:** Pydantic `BaseModel` provides strict type enforcement, JSON serialization, and sanitization. The composite string ID (`repo#number`) allows primary key indexing in SQLite and prevents cross-repository number collisions.
- **Access Pattern:** Inserted once on ingestion; updated during processing lifecycle.

---

### `Facts`
- **Purpose:** Deterministic, non-AI extracted heuristics from the item payload.
- **Shape:**
  ```python
  class Facts(BaseModel):
      has_reproduction: bool
      has_traceback: bool
      lines_added: int
      lines_deleted: int
      tests_modified: bool
      docs_modified: bool
      is_first_time_contributor: bool
      body_length: int
  ```
- **Why this structure:** Fast boolean flags extracted using zero-cost regex and git diff parsers. Feeds directly into prompt construction so the decider model does not waste attention tokens re-computing trivial facts.
- **Size:** Fixed-size tuple/struct (~100 bytes in memory).

---

### `State`
- **Purpose:** The normalized, bounded context supplied to the local Strands Decider 2B.
- **Shape:**
  ```python
  class State(BaseModel):
      item_id: str
      kind: Literal["issue", "pr"]
      title: str
      summary: str  # Truncated description (max 200 tokens)
      facts: Facts
      code_snippet: Optional[str] = None  # Truncated diff/traceback (max 200 tokens)
      total_tokens: int = Field(le=450)
  ```
- **Trade-off:** Strict cap of `<= 450 tokens`. We sacrifice full conversation history and giant stack traces in exchange for predictable, low-latency CPU forward passes (< 300ms) that never trigger OOM on 16GB developer laptops.

---

### `Question` & `DeciderResult`
- **Purpose:** Standardized interface matching Strands Decider 2B's dual question format (`choice` and `noul`).
- **Shape:**
  ```python
  class Question(BaseModel):
      id: str  # e.g., "Q1_TRIAGE_ACTION", "N1_HAS_MINIMAL_REPRO"
      type: Literal["choice", "noul"]
      prompt: str
      options: Optional[List[str]] = None  # For choice questions

  class DeciderResult(BaseModel):
      question_id: str
      winner: str  # Winning option label or "yes"/"no"
      probabilities: Dict[str, float]
      calibrated_confidence: float  # Range: [0.0, 1.0]
      latency_ms: float
  ```
- **Why this structure:** Direct correspondence to the logit output of Strands Decider 2B. Storing full probability distributions (not just winner) is required for threshold gating and Brier score calibration analytics.

---

### `GateVerdict` & `ActionPlan`
- **Purpose:** Output of the `ConfidenceBandHandler` policy engine.
- **Shape:**
  ```python
  class Band(str, Enum):
      HIGH = "HIGH"        # confidence >= 0.85
      MEDIUM = "MEDIUM"    # 0.60 <= confidence < 0.85
      LOW = "LOW"          # confidence < 0.60

  class ActionKind(str, Enum):
      PROCEED = "PROCEED"  # Execute planned action
      CONFIRM = "CONFIRM"  # Queue for maintainer manual confirmation
      GUIDE = "GUIDE"      # Escalate to Bedrock for coaching draft
      DENY = "DENY"        # Reject action due to safety/policy invariant

  class ActionPlan(BaseModel):
      item_id: str
      band: Band
      action: ActionKind
      suggested_labels: List[str]
      draft_comment: Optional[str]
      escalate_to_bedrock: bool
      reasoning: str
  ```
- **Why this structure:** Strongly typed enum actions guarantee that downstream execution code cannot execute arbitrary mutations. Every action requires explicit classification.

---

## 2. SQLite Database Schema (`src/slopgate/store/schema.sql`)

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    repo TEXT NOT NULL,
    number INTEGER NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    author TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    raw_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS receipts (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL REFERENCES items(id),
    band TEXT NOT NULL,
    verdict TEXT NOT NULL,
    decider_confidence REAL NOT NULL,
    bedrock_called INTEGER DEFAULT 0,
    action_plan_json TEXT NOT NULL,
    dry_run INTEGER DEFAULT 1,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS calibration_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    question_id TEXT NOT NULL,
    predicted_prob REAL NOT NULL,
    actual_outcome INTEGER,  -- 1 or 0 for Brier scoring
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
CREATE INDEX IF NOT EXISTS idx_receipts_item ON receipts(item_id);
```

### Access Pattern & Concurrency
- **Writes:** Single local worker thread handles item ingestion and receipts.
- **Reads:** CLI commands (`slopgate report`, `slopgate status`) and Next.js REST API read concurrently.
- **WAL Mode (`PRAGMA journal_mode = WAL`):** Readers do not block writers and writers do not block readers. Zero deadlocks under local single-machine operation.
