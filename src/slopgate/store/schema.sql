-- SlopGate SQLite Database Schema
-- Follows: architecture.md §5.3, docs/defense/04_DATA.md

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  repo TEXT NOT NULL,
  number INTEGER NOT NULL,
  type TEXT NOT NULL,
  title TEXT,
  body TEXT,
  created_at TEXT,
  state_text TEXT,
  state_hash TEXT,
  status TEXT NOT NULL DEFAULT 'queued',   -- queued|processing|decided|executed|pending_approval|flagged|dismissed|error
  processing_started_at TEXT,
  raw_json TEXT NOT NULL,
  UNIQUE(repo, number)
);

CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id INTEGER REFERENCES items(id),
  question_id TEXT NOT NULL,
  qtype TEXT NOT NULL,
  question_text_hash TEXT NOT NULL,
  state_hash TEXT,
  answer TEXT,
  probs_json TEXT,
  confidence REAL,
  band TEXT,
  gate_action TEXT,
  gate_reason TEXT,
  latency_ms REAL,
  model_id TEXT,
  from_cache INTEGER DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_decisions_cache ON decisions(question_id, question_text_hash, model_id);
CREATE INDEX IF NOT EXISTS idx_decisions_state_cache ON decisions(state_hash, question_id, question_text_hash, model_id);
CREATE INDEX IF NOT EXISTS idx_decisions_item ON decisions(item_id);

CREATE TABLE IF NOT EXISTS actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id INTEGER NOT NULL REFERENCES items(id),
  tool TEXT NOT NULL,
  args_json TEXT,
  handler_result TEXT,                     -- proceed|proceed_soft|confirm|guide|deny
  executed INTEGER DEFAULT 0,
  dry_run INTEGER DEFAULT 1,
  idempotency_key TEXT UNIQUE,             -- e.g. repo#num:label:needs-info
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_actions_item ON actions(item_id);

CREATE TABLE IF NOT EXISTS pending_approvals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id INTEGER NOT NULL REFERENCES items(id),
  proposed_plan_json TEXT NOT NULL,
  receipt_md TEXT,
  status TEXT DEFAULT 'pending',           -- pending|approved|rejected
  decided_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_pending_item ON pending_approvals(item_id);

CREATE TABLE IF NOT EXISTS escalations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id INTEGER NOT NULL REFERENCES items(id),
  purpose TEXT NOT NULL,                   -- draft_reply|reason_on_ambiguous|baseline
  bedrock_model TEXT,
  tokens_in INTEGER,
  tokens_out INTEGER,
  latency_ms REAL,
  est_cost_usd REAL,
  output_text TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_escalations_item ON escalations(item_id);

CREATE TABLE IF NOT EXISTS ground_truth (
  item_id INTEGER PRIMARY KEY REFERENCES items(id),
  label TEXT NOT NULL,
  source TEXT NOT NULL                     -- 'proxy' | 'gold'
);
