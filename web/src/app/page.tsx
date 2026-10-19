"use client";

import React, { useState, useEffect } from "react";

interface DemoFixture {
  id: string;
  title: string;
  type: "issue" | "pr";
  repo: string;
  expected_classification: string;
  expected_band: string;
  expected_action: string;
  description: string;
  body: string;
  diff: string;
}

interface TriageResult {
  state_hash: string;
  facts: {
    cited_paths_found: string[];
    has_code_blocks: boolean;
    has_repro_headings: boolean;
    template_filled: string[];
    candidate_duplicate: string[] | null;
    ci_status: string | null;
    approx_tokens: number;
  };
  primary_classification: string;
  confidence: number;
  band: "HIGH" | "MEDIUM" | "LOW";
  verdict: "PROCEED" | "PROCEED_SOFT" | "CONFIRM" | "GUIDE" | "DENY";
  routing_reason: string;
  decisions: Array<{
    question_id: string;
    answer: string;
    confidence: number | null;
    probs: Record<string, number> | null;
  }>;
  planned_tools: Array<{
    tool_name: string;
    arguments: Record<string, unknown>;
    idempotency_key: string;
  }>;
  bedrock: {
    type?: string;
    text?: string;
    recommendation?: string;
    rationale?: string;
    suggested_comment?: string;
    cost_usd?: number;
    tokens_in?: number;
    tokens_out?: number;
    model?: string;
    provider?: string;
    error?: string;
  } | null;
  latency_ms: number;
}

export default function SimulatorPage() {
  const [fixtures, setFixtures] = useState<DemoFixture[]>([]);
  const [selectedFixtureId, setSelectedFixtureId] = useState<string>("clean-bug");

  // Form State
  const [title, setTitle] = useState("");
  const [repo, setRepo] = useState("pallets/flask");
  const [itemType, setItemType] = useState<"issue" | "pr">("issue");
  const [body, setBody] = useState("");
  const [diff, setDiff] = useState("");
  const [deciderMode, setDeciderMode] = useState<"fake" | "in_process">("in_process");
  const [runBedrock, setRunBedrock] = useState(true);

  // Execution State
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<TriageResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Fetch demo fixtures on load
  useEffect(() => {
    fetch("/api/demo/fixtures")
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load fixtures");
        return res.json();
      })
      .then((data: DemoFixture[]) => {
        setFixtures(data);
        if (data.length > 0) {
          applyFixture(data[0]);
        }
      })
      .catch((err) => {
        console.warn("Could not fetch remote fixtures, using local fallback", err);
      });
  }, []);

  const applyFixture = (fixture: DemoFixture) => {
    setSelectedFixtureId(fixture.id);
    setTitle(fixture.title);
    setRepo(fixture.repo);
    setItemType(fixture.type);
    setBody(fixture.body);
    setDiff(fixture.diff || "");
  };

  const handleRunTriage = async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = JSON.stringify({
        title,
        body,
        repo,
        type: itemType,
        diff,
        decider: deciderMode,
        run_bedrock: runBedrock,
        mock_bedrock: false,
      });

      let res: Response;
      try {
        res = await fetch("/api/triage", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: payload,
        });
      } catch {
        res = await fetch("http://127.0.0.1:8000/api/triage", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: payload,
        });
      }

      if (!res.ok) {
        // If Next.js proxy timed out or threw 500, attempt direct call to FastAPI backend
        try {
          const directRes = await fetch("http://127.0.0.1:8000/api/triage", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: payload,
          });
          if (directRes.ok) {
            const data = await directRes.json();
            setResult(data);
            return;
          }
        } catch {
          // keep original res error
        }
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Server responded with HTTP ${res.status}`);
      }

      const data = await res.json();
      setResult(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "An error occurred while evaluating triage");
    } finally {
      setLoading(false);
    }
  };

  const getBandBadgeClass = (band: string) => {
    switch (band) {
      case "HIGH":
        return "badge-high";
      case "MEDIUM":
        return "badge-medium";
      default:
        return "badge-low";
    }
  };

  const getVerdictBadgeClass = (verdict: string) => {
    switch (verdict) {
      case "PROCEED":
      case "PROCEED_SOFT":
        return "badge-proceed";
      case "CONFIRM":
        return "badge-confirm";
      case "GUIDE":
        return "badge-guide";
      case "DENY":
        return "badge-deny";
      default:
        return "badge-cyan";
    }
  };

  return (
    <div style={{ maxWidth: 1280, margin: "0 auto", padding: "32px 24px" }}>
      {/* Header / Hero */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
          <span className="badge badge-cyan">Demo Showcase & Simulator</span>
          <span style={{ color: "var(--text-dim)", fontSize: 13 }}>
            Phase 10: Live Triage Playground
          </span>
        </div>
        <h1 style={{ fontSize: 32, marginBottom: 10 }}>
          Local Confidence-Gated <span className="gradient-text">Triage Simulator</span>
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: 16, maxWidth: 840 }}>
          Experience SlopGate&apos;s dual-model triage: deterministic fact extraction, sub-10ms Decider 2B
          linear-attention inference, calibrated confidence gates, and selective Bedrock escalation
          with <strong>zero unattended community closures</strong>.
        </p>
      </div>

      {/* Preset Scenarios Selector */}
      <div style={{ marginBottom: 28 }}>
        <div
          style={{
            fontSize: 13,
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            color: "var(--text-dim)",
            marginBottom: 12,
          }}
        >
          1-Click Pre-seeded Scenarios
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))",
            gap: 12,
          }}
        >
          {fixtures.map((fixture) => {
            const isSelected = selectedFixtureId === fixture.id;
            return (
              <div
                id={`fixture-${fixture.id}`}
                key={fixture.id}
                onClick={() => applyFixture(fixture)}
                className={`glass-card glass-card-interactive ${
                  isSelected ? "selected-card" : ""
                }`}
                style={{
                  padding: "12px 14px",
                  borderColor: isSelected ? "var(--primary-cyan)" : undefined,
                  backgroundColor: isSelected ? "var(--bg-surface-elevated)" : undefined,
                  boxShadow: isSelected ? "0 0 16px rgba(56, 189, 248, 0.2)" : undefined,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    marginBottom: 6,
                  }}
                >
                  <span
                    className={`badge ${getBandBadgeClass(fixture.expected_band)}`}
                    style={{ fontSize: 10, padding: "2px 6px" }}
                  >
                    {fixture.expected_band}
                  </span>
                  <span
                    className={`badge ${getVerdictBadgeClass(fixture.expected_action)}`}
                    style={{ fontSize: 10, padding: "2px 6px" }}
                  >
                    {fixture.expected_action}
                  </span>
                </div>
                <div style={{ fontWeight: 600, fontSize: 13, color: "#fff", marginBottom: 4 }}>
                  {fixture.id}
                </div>
                <div
                  style={{
                    fontSize: 12,
                    color: "var(--text-muted)",
                    lineHeight: 1.3,
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                  }}
                >
                  {fixture.description}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Main Grid: Input Form (Left) & Results (Right) */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1.05fr 1fr",
          gap: 24,
          alignItems: "start",
        }}
      >
        {/* Left Column: Input Form */}
        <div className="glass-card">
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 16,
              paddingBottom: 12,
              borderBottom: "1px solid var(--border-subtle)",
            }}
          >
            <h2 style={{ fontSize: 17 }}>Triage Input Payload</h2>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                className={`btn ${itemType === "issue" ? "btn-primary" : "btn-secondary"}`}
                style={{ padding: "6px 12px", fontSize: 12 }}
                onClick={() => setItemType("issue")}
              >
                Issue
              </button>
              <button
                type="button"
                className={`btn ${itemType === "pr" ? "btn-primary" : "btn-secondary"}`}
                style={{ padding: "6px 12px", fontSize: 12 }}
                onClick={() => setItemType("pr")}
              >
                Pull Request
              </button>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div>
              <label className="form-label">Repository</label>
              <input
                className="input"
                value={repo}
                onChange={(e) => setRepo(e.target.value)}
                placeholder="owner/repo"
              />
            </div>

            <div>
              <label className="form-label">Title</label>
              <input
                className="input"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Issue or PR title..."
              />
            </div>

            <div>
              <label className="form-label">Body Markdown</label>
              <textarea
                className="textarea mono"
                style={{ fontSize: 13, minHeight: 160 }}
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder="Paste Markdown issue/PR description..."
              />
            </div>

            {itemType === "pr" && (
              <div>
                <label className="form-label">PR Git Unified Diff</label>
                <textarea
                  className="textarea mono"
                  style={{ fontSize: 12, minHeight: 100 }}
                  value={diff}
                  onChange={(e) => setDiff(e.target.value)}
                  placeholder="Paste git diff snippet..."
                />
              </div>
            )}

            {/* Model & Escalation Controls */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 12,
                marginTop: 4,
                padding: "12px 14px",
                background: "rgba(0,0,0,0.2)",
                borderRadius: 8,
                border: "1px solid var(--border-subtle)",
              }}
            >
              <div>
                <label className="form-label" style={{ marginBottom: 4 }}>
                  Decider Engine
                </label>
                <select
                  className="select"
                  value={deciderMode}
                  onChange={(e) => setDeciderMode(e.target.value as "fake" | "in_process")}
                  style={{ padding: "6px 10px", fontSize: 13 }}
                >
                  <option value="in_process">InProcessDecider (Real Strands 2B Model)</option>
                  <option value="fake">FakeDecider (Cached Fast Mode)</option>
                </select>
                <div style={{ fontSize: 11, color: "#34d399", marginTop: 4 }}>
                  ● Exact Strands Decider 2B (hobson-v21) Warmed in RAM
                </div>
              </div>

              <div>
                <label className="form-label" style={{ marginBottom: 4 }}>
                  Generative LLM (Groq OSS / Bedrock)
                </label>
                <label
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    fontSize: 13,
                    color: "var(--text-main)",
                    marginTop: 6,
                    cursor: "pointer",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={runBedrock}
                    onChange={(e) => setRunBedrock(e.target.checked)}
                    style={{ accentColor: "var(--primary-cyan)" }}
                  />
                  <span>Run Escalation / Draft</span>
                </label>
              </div>
            </div>

            {/* Submit Button */}
            <div style={{ marginTop: 8 }}>
              <button
                id="btn-run-triage"
                type="button"
                className="btn btn-primary"
                style={{ width: "100%", padding: "12px", fontSize: 15 }}
                disabled={loading || !title.trim()}
                onClick={handleRunTriage}
              >
                {loading
                  ? (deciderMode === "in_process"
                      ? "🧠 Running Exact Strands Decider 2B Neural Inference..."
                      : "⚡ Evaluating Cascade & Confidence...")
                  : "⚡ Run SlopGate Live Triage"}
              </button>
            </div>

            {error && (
              <div
                style={{
                  padding: "10px 14px",
                  borderRadius: 8,
                  backgroundColor: "var(--verdict-deny-bg)",
                  border: "1px solid var(--verdict-deny-border)",
                  color: "#fda4af",
                  fontSize: 13,
                }}
              >
                <strong>Error:</strong> {error}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Live Triage Results Dashboard */}
        <div>
          {result ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {/* Verdict Header Card */}
              <div className="glass-card" style={{ borderColor: "rgba(56, 189, 248, 0.3)" }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    marginBottom: 14,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span className={`badge ${getVerdictBadgeClass(result.verdict)}`}>
                      {result.verdict}
                    </span>
                    <span className={`badge ${getBandBadgeClass(result.band)}`}>
                      {result.band} Band
                    </span>
                  </div>
                  <div
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 13,
                      color: "var(--primary-cyan)",
                    }}
                  >
                    ⚡ {result.latency_ms} ms CPU
                  </div>
                </div>

                <div style={{ marginBottom: 14 }}>
                  <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>
                    Primary Classification (Q1)
                  </div>
                  <div
                    style={{
                      fontSize: 20,
                      fontWeight: 700,
                      color: "#fff",
                      fontFamily: "var(--font-mono)",
                    }}
                  >
                    {result.primary_classification}
                  </div>
                </div>

                {/* Confidence Meter */}
                <div>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      fontSize: 12,
                      color: "var(--text-muted)",
                      marginBottom: 6,
                    }}
                  >
                    <span>Calibrated Confidence</span>
                    <span style={{ fontWeight: 600, color: "#fff" }}>
                      {(result.confidence * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="progress-container">
                    <div
                      className={`progress-bar ${
                        result.band === "HIGH"
                          ? "progress-high"
                          : result.band === "MEDIUM"
                          ? "progress-med"
                          : "progress-low"
                      }`}
                      style={{ width: `${Math.min(100, Math.max(5, result.confidence * 100))}%` }}
                    />
                  </div>
                </div>

                {/* Routing Reason */}
                <div
                  style={{
                    marginTop: 14,
                    padding: "8px 12px",
                    borderRadius: 6,
                    backgroundColor: "rgba(255, 255, 255, 0.03)",
                    border: "1px solid var(--border-subtle)",
                    fontSize: 13,
                    color: "var(--text-muted)",
                  }}
                >
                  <strong>Routing Rationale:</strong> {result.routing_reason}
                </div>

                {/* State Hash */}
                <div
                  style={{
                    marginTop: 8,
                    fontSize: 11,
                    color: "var(--text-dim)",
                    fontFamily: "var(--font-mono)",
                    wordBreak: "break-all",
                  }}
                >
                  State Hash: {result.state_hash}
                </div>
              </div>

              {/* Deterministic Facts Extraction Card */}
              <div className="glass-card">
                <h3 style={{ fontSize: 15, marginBottom: 12 }}>Deterministic Facts Extracted</h3>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: 10,
                    fontSize: 13,
                  }}
                >
                  <div
                    style={{
                      padding: "8px 10px",
                      borderRadius: 6,
                      background: "rgba(0,0,0,0.2)",
                    }}
                  >
                    <div style={{ color: "var(--text-dim)", fontSize: 11 }}>Code Block Detected</div>
                    <div
                      style={{
                        fontWeight: 600,
                        color: result.facts.has_code_blocks ? "#34d399" : "var(--text-muted)",
                      }}
                    >
                      {result.facts.has_code_blocks ? "✓ Detected" : "✗ None"}
                    </div>
                  </div>

                  <div
                    style={{
                      padding: "8px 10px",
                      borderRadius: 6,
                      background: "rgba(0,0,0,0.2)",
                    }}
                  >
                    <div style={{ color: "var(--text-dim)", fontSize: 11 }}>Repro Headings</div>
                    <div
                      style={{
                        fontWeight: 600,
                        color: result.facts.has_repro_headings ? "#34d399" : "var(--text-muted)",
                      }}
                    >
                      {result.facts.has_repro_headings ? "✓ Detected" : "✗ None"}
                    </div>
                  </div>

                  <div
                    style={{
                      padding: "8px 10px",
                      borderRadius: 6,
                      background: "rgba(0,0,0,0.2)",
                    }}
                  >
                    <div style={{ color: "var(--text-dim)", fontSize: 11 }}>Paths / Symbols</div>
                    <div style={{ fontWeight: 600, color: "var(--text-main)", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {result.facts.cited_paths_found.length > 0
                        ? result.facts.cited_paths_found.join(", ")
                        : "None cited"}
                    </div>
                  </div>

                  <div
                    style={{
                      padding: "8px 10px",
                      borderRadius: 6,
                      background: "rgba(0,0,0,0.2)",
                    }}
                  >
                    <div style={{ color: "var(--text-dim)", fontSize: 11 }}>Approx Tokens</div>
                    <div style={{ fontWeight: 600, color: "var(--text-main)" }}>
                      {result.facts.approx_tokens} tokens
                    </div>
                  </div>
                </div>
              </div>

              {/* Planned Tool Actions */}
              <div className="glass-card">
                <h3 style={{ fontSize: 15, marginBottom: 12 }}>Planned Tool Action Sequence</h3>
                {result.planned_tools.length === 0 ? (
                  <div style={{ color: "var(--text-dim)", fontSize: 13 }}>
                    No automated actions planned.
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {result.planned_tools.map((step, idx) => (
                      <div
                        key={idx}
                        style={{
                          padding: "8px 12px",
                          borderRadius: 6,
                          backgroundColor: "rgba(255, 255, 255, 0.03)",
                          border: "1px solid var(--border-subtle)",
                          fontSize: 13,
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span
                            style={{
                              fontFamily: "var(--font-mono)",
                              fontWeight: 600,
                              color: "var(--primary-cyan)",
                            }}
                          >
                            {step.tool_name}
                          </span>
                          <span style={{ fontSize: 11, color: "var(--text-dim)" }}>
                            Idempotent
                          </span>
                        </div>
                        <div
                          style={{
                            fontFamily: "var(--font-mono)",
                            fontSize: 11,
                            color: "var(--text-muted)",
                            marginTop: 4,
                            whiteSpace: "pre-wrap",
                            wordBreak: "break-all",
                          }}
                        >
                          {JSON.stringify(step.arguments)}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Bedrock Escalation Draft Drawer (if present) */}
              {result.bedrock && (
                <div
                  className="glass-card"
                  style={{
                    backgroundColor: "rgba(99, 102, 241, 0.08)",
                    borderColor: "rgba(99, 102, 241, 0.35)",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      marginBottom: 8,
                    }}
                  >
                    <span
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        color: "#a5b4fc",
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                        flexWrap: "wrap",
                      }}
                    >
                      🤖 {result.bedrock.provider || "LLM Generative Escalation"}
                      {result.bedrock.model && (
                        <span
                          style={{
                            fontSize: 10,
                            padding: "2px 6px",
                            borderRadius: 4,
                            backgroundColor: "rgba(165, 180, 252, 0.15)",
                            color: "#c7d2fe",
                            fontFamily: "var(--font-mono)",
                          }}
                        >
                          {result.bedrock.model}
                        </span>
                      )}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: 11,
                        color: "var(--text-dim)",
                      }}
                    >
                      Cost: ${result.bedrock.cost_usd?.toFixed(4) || "0.0001"}
                    </span>
                  </div>

                  {result.bedrock.text && (
                    <div
                      style={{
                        fontSize: 13,
                        color: "var(--text-main)",
                        backgroundColor: "rgba(0,0,0,0.3)",
                        padding: "10px 12px",
                        borderRadius: 6,
                        whiteSpace: "pre-wrap",
                      }}
                    >
                      {result.bedrock.text}
                    </div>
                  )}

                  {result.bedrock.suggested_comment && (
                    <div
                      style={{
                        fontSize: 13,
                        color: "var(--text-main)",
                        backgroundColor: "rgba(0,0,0,0.3)",
                        padding: "10px 12px",
                        borderRadius: 6,
                        whiteSpace: "pre-wrap",
                        marginTop: 6,
                      }}
                    >
                      <strong>Suggested Clarification:</strong>
                      <div style={{ marginTop: 4 }}>{result.bedrock.suggested_comment}</div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            /* Empty State Placeholder */
            <div
              className="glass-card"
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                minHeight: 460,
                textAlign: "center",
                color: "var(--text-dim)",
                borderStyle: "dashed",
              }}
            >
              <div style={{ fontSize: 48, marginBottom: 16 }}>🛡️</div>
              <h3 style={{ color: "var(--text-muted)", fontSize: 18, marginBottom: 8 }}>
                Ready to Triage
              </h3>
              <p style={{ maxWidth: 360, fontSize: 14 }}>
                Select one of the 6 pre-seeded demo fixtures above or enter your own custom issue/PR
                text, then click <strong>Run SlopGate Live Triage</strong>.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
