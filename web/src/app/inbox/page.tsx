"use client";

import React, { useState, useEffect, useCallback } from "react";

interface ApprovalStep {
  tool_name: string;
  args?: Record<string, unknown>;
  idempotency_key?: string;
}

interface PendingApproval {
  id: number;
  item_id: number;
  status: "pending" | "approved" | "rejected";
  created_at: string;
  repo?: string;
  number?: number;
  title?: string;
  plan?: {
    steps?: ApprovalStep[];
  };
  receipt_md?: string;
}

interface ReceiptData {
  receipt: Record<string, unknown>;
  markdown: string;
}

export default function ReviewInboxPage() {
  const [approvals, setApprovals] = useState<PendingApproval[]>([]);
  const [activeTab, setActiveTab] = useState<"pending" | "approved" | "rejected">("pending");
  const [loading, setLoading] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  // Drawer / Receipt State
  const [selectedReceipt, setSelectedReceipt] = useState<ReceiptData | null>(null);
  const [receiptLoading, setReceiptLoading] = useState(false);
  const [activeItemTitle, setActiveItemTitle] = useState<string>("");

  const fetchApprovals = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/approvals?status=${activeTab}`);
      if (!res.ok) throw new Error("Failed to load approvals");
      const data = await res.json();
      setApprovals(data);
    } catch (err) {
      console.error("Error loading approvals:", err);
    } finally {
      setLoading(false);
    }
  }, [activeTab]);

  useEffect(() => {
    fetchApprovals();
  }, [fetchApprovals]);

  const handleAction = async (approvalId: number, action: "approve" | "reject", live: boolean) => {
    try {
      const res = await fetch(`/api/approvals/${approvalId}/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, live }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Action failed with ${res.status}`);
      }

      setActionMessage(
        `Approval #${approvalId} successfully marked as ${action} (${live ? "live executed" : "dry-run"}).`
      );
      setTimeout(() => setActionMessage(null), 4000);
      fetchApprovals();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Error executing action");
    }
  };

  const handleViewReceipt = async (itemId: number, title?: string) => {
    setActiveItemTitle(title || `Item #${itemId}`);
    setReceiptLoading(true);
    try {
      const res = await fetch(`/api/items/${itemId}/receipt`);
      if (!res.ok) throw new Error("Failed to load receipt");
      const data = await res.json();
      setSelectedReceipt(data);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to load receipt");
    } finally {
      setReceiptLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 1280, margin: "0 auto", padding: "32px 24px" }}>
      {/* Page Header */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
          <span className="badge badge-confirm">Maintainer Invariant</span>
          <span style={{ color: "var(--text-dim)", fontSize: 13 }}>
            Zero Unattended Closes Guarantee
          </span>
        </div>
        <h1 style={{ fontSize: 32, marginBottom: 10 }}>
          Maintainer <span className="gradient-text">Review Queue</span>
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: 16, maxWidth: 840 }}>
          High-stakes mutations (closing issues/PRs or low-confidence escalations) are strictly
          gated. Maintainers can inspect deterministic decision receipts, verify linear-attention
          cascade outputs, and execute approved plans with 1-click.
        </p>
      </div>

      {actionMessage && (
        <div
          style={{
            marginBottom: 20,
            padding: "12px 16px",
            borderRadius: 8,
            backgroundColor: "rgba(16, 185, 129, 0.15)",
            border: "1px solid rgba(16, 185, 129, 0.35)",
            color: "#6ee7b7",
            fontSize: 14,
          }}
        >
          ✓ {actionMessage}
        </div>
      )}

      {/* Tabs */}
      <div
        style={{
          display: "flex",
          gap: 12,
          borderBottom: "1px solid var(--border-subtle)",
          paddingBottom: 12,
          marginBottom: 24,
        }}
      >
        <button
          className={`btn ${activeTab === "pending" ? "btn-primary" : "btn-secondary"}`}
          onClick={() => setActiveTab("pending")}
          style={{ padding: "8px 16px" }}
        >
          Pending Review ({approvals.length})
        </button>
        <button
          className={`btn ${activeTab === "approved" ? "btn-primary" : "btn-secondary"}`}
          onClick={() => setActiveTab("approved")}
          style={{ padding: "8px 16px" }}
        >
          Approved
        </button>
        <button
          className={`btn ${activeTab === "rejected" ? "btn-primary" : "btn-secondary"}`}
          onClick={() => setActiveTab("rejected")}
          style={{ padding: "8px 16px" }}
        >
          Rejected
        </button>
      </div>

      {/* Table / Cards */}
      {loading ? (
        <div style={{ color: "var(--text-muted)", padding: 40, textAlign: "center" }}>
          Loading review queue...
        </div>
      ) : approvals.length === 0 ? (
        <div
          className="glass-card"
          style={{
            textAlign: "center",
            padding: "48px 24px",
            color: "var(--text-dim)",
          }}
        >
          <div style={{ fontSize: 36, marginBottom: 12 }}>✓</div>
          <h3 style={{ color: "var(--text-muted)", fontSize: 18, marginBottom: 6 }}>
            Inbox Clear
          </h3>
          <p style={{ fontSize: 14 }}>
            No {activeTab} maintainer approval requests found in database.
          </p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {approvals.map((app) => (
            <div
              key={app.id}
              className="glass-card"
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 12,
                borderLeft: "4px solid #f59e0b",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  flexWrap: "wrap",
                  gap: 12,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span className="badge badge-confirm">Requires Sign-off</span>
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 13,
                      color: "var(--primary-cyan)",
                    }}
                  >
                    {app.repo ? `${app.repo}#${app.number}` : `Item #${app.item_id}`}
                  </span>
                  <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
                    Approval #{app.id} • {app.created_at}
                  </span>
                </div>

                <div style={{ display: "flex", gap: 8 }}>
                  <button
                    id={`btn-view-receipt-${app.id}`}
                    className="btn btn-secondary"
                    style={{ padding: "6px 12px", fontSize: 13 }}
                    onClick={() => handleViewReceipt(app.item_id, app.title)}
                  >
                    📄 View Full Receipt
                  </button>

                  {activeTab === "pending" && (
                    <>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: "6px 12px", fontSize: 13 }}
                        onClick={() => handleAction(app.id, "approve", false)}
                      >
                        Approve (Dry Run)
                      </button>
                      <button
                        className="btn btn-success"
                        style={{ padding: "6px 12px", fontSize: 13 }}
                        onClick={() => handleAction(app.id, "approve", true)}
                      >
                        Approve & Execute (Live)
                      </button>
                      <button
                        className="btn btn-danger"
                        style={{ padding: "6px 12px", fontSize: 13 }}
                        onClick={() => handleAction(app.id, "reject", false)}
                      >
                        Reject
                      </button>
                    </>
                  )}
                </div>
              </div>

              {app.title && (
                <div style={{ fontSize: 16, fontWeight: 600, color: "#fff" }}>
                  {app.title}
                </div>
              )}

              {/* Proposed Steps */}
              {app.plan?.steps && app.plan.steps.length > 0 && (
                <div
                  style={{
                    backgroundColor: "rgba(0,0,0,0.25)",
                    borderRadius: 8,
                    padding: "10px 14px",
                    border: "1px solid var(--border-subtle)",
                  }}
                >
                  <div
                    style={{
                      fontSize: 12,
                      fontWeight: 600,
                      color: "var(--text-muted)",
                      marginBottom: 6,
                    }}
                  >
                    Proposed Automated Steps ({app.plan.steps.length}):
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {app.plan.steps.map((st, i) => (
                      <div
                        key={i}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                          fontFamily: "var(--font-mono)",
                          fontSize: 12,
                        }}
                      >
                        <span style={{ color: "var(--primary-cyan)" }}>↳ {st.tool_name}</span>
                        <span style={{ color: "var(--text-dim)" }}>
                          {JSON.stringify(st.args || {})}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Slide-over Drawer / Modal for Receipt */}
      {(selectedReceipt || receiptLoading) && (
        <div className="modal-overlay" onClick={() => setSelectedReceipt(null)}>
          <div className="drawer" onClick={(e) => e.stopPropagation()}>
            <div
              style={{
                padding: "20px 24px",
                borderBottom: "1px solid var(--border-subtle)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <div>
                <h3 style={{ fontSize: 17, color: "#fff" }}>Decision Receipt</h3>
                <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                  {activeItemTitle}
                </div>
              </div>
              <button
                id="btn-close-drawer"
                className="btn btn-secondary"
                style={{ padding: "6px 12px", fontSize: 12 }}
                onClick={() => setSelectedReceipt(null)}
              >
                ✕ Close
              </button>
            </div>

            <div style={{ padding: "24px", overflowY: "auto", flex: 1 }}>
              {receiptLoading ? (
                <div style={{ color: "var(--text-muted)", textAlign: "center", padding: 40 }}>
                  Loading decision receipt...
                </div>
              ) : (
                <pre
                  className="mono"
                  style={{
                    backgroundColor: "#070b14",
                    padding: 16,
                    borderRadius: 8,
                    border: "1px solid var(--border-subtle)",
                    fontSize: 12,
                    lineHeight: 1.5,
                    color: "var(--text-main)",
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-all",
                  }}
                >
                  {selectedReceipt?.markdown}
                </pre>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
