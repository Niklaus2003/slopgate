import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "SlopGate | Confidence-Gated Autonomous Issue & PR Triage",
  description:
    "Local 2B Decider running linear-attention inference on CPU with Bedrock ambiguity escalation and zero unattended community closures.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        {/* Top Navbar */}
        <header
          style={{
            position: "sticky",
            top: 0,
            zIndex: 100,
            backgroundColor: "rgba(7, 11, 20, 0.8)",
            backdropFilter: "blur(12px)",
            borderBottom: "1px solid var(--border-subtle)",
          }}
        >
          <div
            style={{
              maxWidth: 1280,
              margin: "0 auto",
              padding: "14px 24px",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 20,
            }}
          >
            {/* Brand */}
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <div
                style={{
                  width: 38,
                  height: 38,
                  borderRadius: 10,
                  background: "linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 20,
                  boxShadow: "0 0 16px rgba(14, 165, 233, 0.4)",
                }}
              >
                🛡️
              </div>
              <div>
                <Link
                  href="/"
                  style={{
                    fontSize: 18,
                    fontWeight: 700,
                    letterSpacing: "-0.02em",
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                  }}
                >
                  <span className="gradient-text">SlopGate</span>
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 600,
                      backgroundColor: "rgba(56, 189, 248, 0.15)",
                      color: "var(--primary-cyan)",
                      padding: "2px 6px",
                      borderRadius: 4,
                      border: "1px solid rgba(56, 189, 248, 0.3)",
                    }}
                  >
                    v0.1.0-alpha
                  </span>
                </Link>
                <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
                  Confidence-Gated Autonomous Triage
                </div>
              </div>
            </div>

            {/* Navigation Links */}
            <nav style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Link
                id="nav-simulator"
                href="/"
                className="btn btn-secondary"
                style={{ padding: "8px 14px", fontSize: 13 }}
              >
                ⚡ Simulator
              </Link>
              <Link
                id="nav-inbox"
                href="/inbox"
                className="btn btn-secondary"
                style={{ padding: "8px 14px", fontSize: 13 }}
              >
                📥 Review Inbox
              </Link>
              <Link
                id="nav-analytics"
                href="/analytics"
                className="btn btn-secondary"
                style={{ padding: "8px 14px", fontSize: 13 }}
              >
                📊 Calibration & Safety
              </Link>
            </nav>

            {/* System Status Pill */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "6px 12px",
                borderRadius: 9999,
                backgroundColor: "rgba(16, 185, 129, 0.08)",
                border: "1px solid rgba(16, 185, 129, 0.25)",
                fontSize: 12,
              }}
            >
              <span className="status-dot" />
              <span style={{ color: "#34d399", fontWeight: 500 }}>Decider 2B CPU</span>
              <span style={{ color: "var(--text-dim)" }}>|</span>
              <span style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                0.0% False-Reject Invariant
              </span>
            </div>
          </div>
        </header>

        {/* Main Content Area */}
        <main style={{ minHeight: "calc(100vh - 140px)" }}>{children}</main>

        {/* Global Footer */}
        <footer
          style={{
            borderTop: "1px solid var(--border-subtle)",
            backgroundColor: "rgba(7, 11, 20, 0.9)",
            padding: "24px 0",
            fontSize: 13,
            color: "var(--text-dim)",
          }}
        >
          <div
            style={{
              maxWidth: 1280,
              margin: "0 auto",
              padding: "0 24px",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: 12,
            }}
          >
            <div>
              SlopGate: Autonomous GitHub Triage Guardrail. Zero unattended closures on legitimate
              open-source work.
            </div>
            <div style={{ display: "flex", gap: 16 }}>
              <span>Pure CPU PyTorch</span>
              <span>•</span>
              <span>FastAPI REST API</span>
              <span>•</span>
              <span>Amazon Bedrock Escalation</span>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
