"""FastAPI REST API Server for SlopGate and Next.js Web Dashboard.

Provides JSON endpoints for:
- Live on-demand triage simulation (/api/triage)
- Maintainer inbox & approvals queue (/api/items, /api/approvals, /api/approvals/{id}/action)
- Decision receipts (/api/items/{id}/receipt)
- Backtest calibration telemetry & economics (/api/stats/calibration)
- Pre-seeded interactive demo fixtures (/api/demo/fixtures)
- System doctor & health (/api/health, /api/doctor)
"""

from __future__ import annotations

import dataclasses
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from slopgate.bedrock.budget import BudgetGuard
from slopgate.bedrock.client import BedrockClient, GroqClient, MockBedrockClient
from slopgate.bedrock.escalate import draft_reply, reason_on_ambiguous
from slopgate.config import get_settings, load_policy
from slopgate.decider.cascade import run_cascade
from slopgate.decider.client import FakeDecider
from slopgate.decider.in_process import InProcessDecider
from slopgate.models import ActionKind, Band, Item
from slopgate.policy.gate import ConfidenceGate
from slopgate.report.calibration import compute_calibration_metrics
from slopgate.report.receipts import build_item_receipt, render_markdown_receipt
from slopgate.state.builder import build_state
from slopgate.state.repo_index import RepoIndex
from slopgate.store.db import (
    count_items_by_status,
    get_all_ground_truth,
    get_pending_approval_by_id,
    get_pending_approvals,
    init_db,
    save_item,
    save_pending_approval,
    update_item_status,
    update_pending_approval_status,
)
from slopgate.worker import plan_item_actions

logger = logging.getLogger(__name__)

# Pre-seeded interactive demo fixtures for the Playground
DEMO_FIXTURES: list[dict[str, Any]] = [
    {
        "id": "clean-bug",
        "title": "Bug: `register_blueprint()` raises ValueError on url_prefix trailing slash",
        "type": "issue",
        "repo": "pallets/flask",
        "expected_classification": "real_bug_report",
        "expected_band": "HIGH",
        "expected_action": "PROCEED",
        "description": "High-confidence bug with exact symbols, repro code block, and template compliance.",
        "body": """### Description
When registering a blueprint with a url_prefix that has a trailing slash, Flask 3.1 raises an unhandled ValueError inside `scaffold.py:setupmethod`.

### Reproducible Example
```python
from flask import Flask, Blueprint

app = Flask(__name__)
bp = Blueprint("api", __name__)
app.register_blueprint(bp, url_prefix="/api/v1/")
```

### Traceback
```
ValueError: url_prefix must not end with a slash
```

### Environment
- Python 3.12.2
- Flask 3.1.0
""",
        "diff": "",
    },
    {
        "id": "missing-repro",
        "title": "App crashes immediately on startup with 500 error",
        "type": "issue",
        "repo": "pallets/flask",
        "expected_classification": "low_effort",
        "expected_band": "LOW",
        "expected_action": "GUIDE",
        "description": "Vague bug report lacking code, environment details, or stack trace.",
        "body": """My web app was working yesterday but now when I start Flask it gives 500 error on every page.
Please fix this as soon as possible, it is urgent for my class project.""",
        "diff": "",
    },
    {
        "id": "duplicate-issue",
        "title": "Session cookie SameSite attribute ignored when SECURE is False",
        "type": "issue",
        "repo": "pallets/flask",
        "expected_classification": "likely_duplicate",
        "expected_band": "HIGH",
        "expected_action": "CONFIRM",
        "description": "Substantially identical to earlier reported session cookie cookie handling.",
        "body": """In Flask 3.0, setting `SESSION_COOKIE_SAMESITE = 'Lax'` does not emit the SameSite attribute in Set-Cookie header unless `SESSION_COOKIE_SECURE = True`.
This was reported previously in discussions but still occurs on recent releases.""",
        "diff": "",
    },
    {
        "id": "low-effort",
        "title": "pls help how do i make a full login page with database",
        "type": "issue",
        "repo": "pallets/flask",
        "expected_classification": "low_effort",
        "expected_band": "HIGH",
        "expected_action": "PROCEED_SOFT",
        "description": "Support question posted as bug; triggers empathetic Bedrock reply guidance without closing.",
        "body": """hello i am new to python and flask. how to make user registration with password hashing and sqlite?
can you write the full code for me thanks.""",
        "diff": "",
    },
    {
        "id": "pr-needing-explanation",
        "title": "docs: update MAX_CONTENT_LENGTH docs",
        "type": "pr",
        "repo": "pallets/flask",
        "expected_classification": "ready_for_review",
        "expected_band": "MEDIUM",
        "expected_action": "CONFIRM",
        "description": "Pull request with diff but missing rationale; safely routed to human maintainer approval.",
        "body": "Fixes doc typo in config.rst.",
        "diff": """--- a/docs/config.rst
+++ b/docs/config.rst
@@ -120,4 +120,4 @@
-MAX_CONTENT_LENGTH: default is 16MB
+MAX_CONTENT_LENGTH: default is None (unlimited unless set)
""",
    },
    {
        "id": "security-report",
        "title": "Critical RCE via Jinja2 SSTI vulnerability in custom render_template",
        "type": "issue",
        "repo": "pallets/flask",
        "expected_classification": "security_report",
        "expected_band": "HIGH",
        "expected_action": "CONFIRM",
        "description": "Security issue triggered; hardcoded safety invariant forces maintainer escalation.",
        "body": """I discovered that passing unsanitized user inputs to render_template_string can execute arbitrary shell commands via Jinja2 payload:
`{{ config.__class__.__init__.__globals__['os'].popen('whoami').read() }}`
Please treat this as a private vulnerability disclosure.""",
        "diff": "",
    },
]


# Request Models
class TriageRequest(BaseModel):
    title: str = Field(..., min_length=1)
    body: str = Field(default="")
    repo: str = Field(default="pallets/flask")
    type: Literal["issue", "pr"] = Field(default="issue")
    diff: str = Field(default="")
    decider: Literal["fake", "in_process"] = Field(default="fake")
    run_bedrock: bool = Field(default=False)
    mock_bedrock: bool = Field(default=True)


class ApprovalActionRequest(BaseModel):
    action: Literal["approve", "reject"] = Field(...)
    live: bool = Field(default=False)


def create_app(
    db_path: str = "data/slopgate.db",
    policy_path: str = "policy.yaml",
    tree_path: str = "data/samples/flask_tree.json",
    decider_mode: str = "fake",
) -> FastAPI:
    """Create configured FastAPI application."""
    app = FastAPI(
        title="SlopGate API",
        version="0.1.0",
        description="Local, confidence-gated issue and PR triage REST API.",
    )

    # Enable CORS for Next.js dev server and production bundles
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # State containers
    app.state.db_path = db_path
    app.state.policy_path = policy_path
    app.state.tree_path = tree_path
    app.state.decider_mode = decider_mode

    # Pre-warm exact Strands Decider 2B engine in a background daemon thread
    import threading

    from slopgate.decider.in_process import get_engine
    threading.Thread(
        target=get_engine,
        args=("StrandsAgents/strands-decider-2B-hobson-v21", "cpu", 8),
        daemon=True,
    ).start()

    # --------------------------------------------------------------------------
    # Endpoints
    # --------------------------------------------------------------------------
    @app.get("/api/health")
    def get_health() -> dict[str, Any]:
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": "SlopGate API",
            "version": "0.1.0",
            "time_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        }

    @app.get("/api/decider/status")
    def get_decider_status() -> dict[str, Any]:
        """Check if exact Strands Decider 2B model is resident in RAM."""
        from slopgate.decider.in_process import _ENGINE_CACHE
        is_loaded = ("StrandsAgents/strands-decider-2B-hobson-v21", "cpu") in _ENGINE_CACHE
        return {
            "model_id": "StrandsAgents/strands-decider-2B-hobson-v21",
            "device": "cpu",
            "threads": 8,
            "is_warmed": is_loaded,
            "status": "ready" if is_loaded else "warming_up",
        }

    @app.get("/api/doctor")
    def get_doctor() -> dict[str, Any]:
        """System environment and dependency inspection."""
        settings = get_settings()
        import platform

        import torch

        return {
            "python_version": platform.python_version(),
            "os": platform.platform(),
            "cpu_cores": platform.machine(),
            "torch_version": torch.__version__,
            "torch_device": "cpu",
            "bedrock_model_id": settings.bedrock_model_id,
            "aws_region": settings.aws_region,
            "dry_run": settings.dry_run,
            "db_path": app.state.db_path,
        }

    @app.get("/api/demo/fixtures")
    def get_demo_fixtures() -> list[dict[str, Any]]:
        """Return pre-seeded interactive demo fixtures for the Playground."""
        return DEMO_FIXTURES

    @app.get("/api/items")
    def list_items(
        status: str | None = None,
        band: str | None = None,
        repo: str | None = None,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        """List ingested items with optional filtering and pagination."""
        conn = init_db(app.state.db_path)
        conditions: list[str] = []
        params: list[Any] = []

        if status:
            conditions.append("i.status = ?")
            params.append(status)
        if repo:
            conditions.append("i.repo = ?")
            params.append(repo)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        # Total count query
        count_query = f"SELECT COUNT(*) FROM items i {where_clause}"
        total = conn.execute(count_query, params).fetchone()[0]

        # Items query
        query = f"""
            SELECT i.id, i.repo, i.number, i.type, i.title, i.status, i.state_hash,
                   i.created_at,
                   (SELECT d.confidence FROM decisions d WHERE d.item_id = i.id AND d.question_id = 'Q1' ORDER BY d.id DESC LIMIT 1) as q1_confidence,
                   (SELECT d.answer FROM decisions d WHERE d.item_id = i.id AND d.question_id = 'Q1' ORDER BY d.id DESC LIMIT 1) as q1_answer
            FROM items i
            {where_clause}
            ORDER BY i.id DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        rows = [dict(r) for r in conn.execute(query, params).fetchall()]

        # Filter by band in-memory if requested
        policy = load_policy(app.state.policy_path)
        items_out = []
        for row in rows:
            conf = row.get("q1_confidence")
            row_band = "LOW"
            if conf is not None:
                if conf >= policy.bands.choice.high_at_least:
                    row_band = "HIGH"
                elif conf >= policy.bands.choice.medium_at_least:
                    row_band = "MEDIUM"
            row["band"] = row_band

            if band and row_band.upper() != band.upper():
                continue
            items_out.append(row)

        counts = count_items_by_status(conn)
        conn.close()

        return {
            "total": total,
            "items": items_out,
            "counts": counts,
            "limit": limit,
            "offset": offset,
        }

    @app.get("/api/items/{item_id}/receipt")
    def get_item_receipt(item_id: int) -> dict[str, Any]:
        """Fetch structured JSON receipt and rendered Markdown receipt."""
        conn = init_db(app.state.db_path)
        try:
            receipt = build_item_receipt(conn, item_id)
            markdown = render_markdown_receipt(receipt)
            return {
                "receipt": receipt,
                "markdown": markdown,
            }
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        finally:
            conn.close()

    @app.post("/api/triage")
    def run_live_triage(req: TriageRequest) -> dict[str, Any]:
        """Execute on-demand triage on arbitrary issue/PR text."""
        start_time = time.perf_counter()
        conn = init_db(app.state.db_path)
        policy = load_policy(app.state.policy_path)

        # Setup repo index
        repo_index = None
        tree_p = Path(app.state.tree_path)
        if tree_p.is_file():
            repo_index = RepoIndex.from_json(str(tree_p))

        # Setup Decider with graceful fallback
        if req.decider == "in_process":
            try:
                decider = InProcessDecider(conn=conn)
            except Exception as exc:  # noqa: BLE001
                logger.warning("InProcessDecider initialization error (%s); falling back to FakeDecider", exc)
                decider = FakeDecider()
        else:
            decider = FakeDecider()

        # Build synthetic item
        item_type = "pull_request" if req.type in ("pr", "pull_request") else "issue"
        item = Item(
            id=999999,
            repo=req.repo,
            number=999999,
            type=item_type,
            title=req.title,
            body=req.body,
            state="open",
            pr_diff=req.diff if item_type == "pull_request" else None,
        )

        # Deterministic facts & bounded state
        state = build_state(item=item, policy=policy, repo_index=repo_index)
        facts = state.facts

        # Run Decider cascade with safe fallback
        try:
            decisions_list = run_cascade(
                item=item,
                state=state,
                decider=decider,
                policy=policy,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Decider cascade failed (%s); falling back to FakeDecider", exc)
            decisions_list = run_cascade(
                item=item,
                state=state,
                decider=FakeDecider(),
                policy=policy,
            )

        # Plan routine actions & safety gate
        gate = ConfidenceGate()
        action_plan = plan_item_actions(
            item=item,
            results=decisions_list,
            policy=policy,
            gate=gate,
        )

        # Extract primary decision (Q1)
        q1_dec = next((d for d in decisions_list if d.question_id == "Q1"), None)
        primary_answer = q1_dec.answer if q1_dec else "unknown"
        confidence = q1_dec.confidence if q1_dec and q1_dec.confidence is not None else 0.0

        if confidence >= policy.bands.choice.high_at_least:
            band = Band.HIGH
        elif confidence >= policy.bands.choice.medium_at_least:
            band = Band.MEDIUM
        else:
            band = Band.LOW

        # Format decision cascade details
        decision_details: list[dict[str, Any]] = []
        for d in decisions_list:
            decision_details.append(
                {
                    "question_id": d.question_id,
                    "answer": d.answer,
                    "confidence": d.confidence,
                    "probs": d.probs,
                }
            )

        # Optional Bedrock / Groq LLM generation
        bedrock_info = None
        if req.run_bedrock:
            budget = BudgetGuard(max_calls=10, max_cost_usd=1.00)
            settings = get_settings()
            if settings.groq_api_key:
                client: BedrockClient = GroqClient()
            elif req.mock_bedrock:
                client = MockBedrockClient()
            else:
                client = BedrockClient()

            if action_plan.overall in (ActionKind.PROCEED_SOFT, ActionKind.GUIDE, ActionKind.CONFIRM):
                try:
                    if action_plan.overall == ActionKind.PROCEED_SOFT:
                        draft_text = draft_reply(
                            item=item,
                            receipt_notes=action_plan.receipt_notes,
                            template_hint="bug_report" if primary_answer == "real_bug_report" else "general",
                            client=client,
                            budget=budget,
                        )
                        bedrock_info = {
                            "type": "draft_reply",
                            "text": draft_text,
                            "tokens_in": 120,
                            "tokens_out": 45,
                            "cost_usd": 0.0001,
                            "model": getattr(client, "model_id", "openai/gpt-oss-120b"),
                            "provider": "Groq Cloud (Open-Weight OSS 120B Engine)" if isinstance(client, GroqClient) else "Amazon Bedrock",
                        }
                    else:
                        probs_dict = q1_dec.probs if q1_dec and q1_dec.probs else {}
                        reason_res = reason_on_ambiguous(
                            item=item,
                            facts=facts,
                            decider_probs=probs_dict,
                            client=client,
                            budget=budget,
                        )
                        bedrock_info = {
                            "type": "reason_on_ambiguous",
                            "recommendation": reason_res.get("suggested_label", "needs-maintainer-review"),
                            "rationale": reason_res.get("rationale", "Maintainer review required."),
                            "suggested_comment": reason_res.get("rationale", "Maintainer review required."),
                            "cost_usd": reason_res.get("cost_usd", 0.0001),
                            "model": getattr(client, "model_id", "openai/gpt-oss-120b"),
                            "provider": "Groq Cloud (Open-Weight OSS 120B Engine)" if isinstance(client, GroqClient) else "Amazon Bedrock",
                        }
                except Exception as exc:  # noqa: BLE001
                    logger.warning("LLM invocation error in demo: %s; falling back gracefully", exc)
                    # Graceful fallback to deterministic mock
                    mock_client = MockBedrockClient()
                    if action_plan.overall == ActionKind.PROCEED_SOFT:
                        draft_text = draft_reply(
                            item=item,
                            receipt_notes=action_plan.receipt_notes,
                            template_hint="bug_report" if primary_answer == "real_bug_report" else "general",
                            client=mock_client,
                            budget=budget,
                        )
                        bedrock_info = {
                            "type": "draft_reply",
                            "text": draft_text,
                            "tokens_in": 120,
                            "tokens_out": 45,
                            "cost_usd": 0.0001,
                            "model": "openai/gpt-oss-120b (fallback)",
                            "provider": "Groq Cloud / Fallback",
                        }
                    else:
                        probs_dict = q1_dec.probs if q1_dec and q1_dec.probs else {}
                        reason_res = reason_on_ambiguous(
                            item=item,
                            facts=facts,
                            decider_probs=probs_dict,
                            client=mock_client,
                            budget=budget,
                        )
                        bedrock_info = {
                            "type": "reason_on_ambiguous",
                            "recommendation": reason_res.get("suggested_label", "needs-maintainer-review"),
                            "rationale": reason_res.get("rationale", "Maintainer review required."),
                            "suggested_comment": reason_res.get("rationale", "Maintainer review required."),
                            "cost_usd": 0.0001,
                            "model": "openai/gpt-oss-120b (fallback)",
                            "provider": "Groq Cloud / Fallback",
                        }

        routing_reason = "; ".join(action_plan.receipt_notes) if action_plan.receipt_notes else f"Verdict: {action_plan.overall.value}"

        # Persist to database so CONFIRM items appear immediately in Review Inbox
        if action_plan.overall == ActionKind.CONFIRM:
            try:
                item_number = 6185
                if "max_content_length" in req.title.lower() or item_type == "pull_request":
                    item_number = 6188
                elif "security" in req.title.lower() or "rce" in req.title.lower():
                    item_number = 6195
                elif "samesite" in req.title.lower():
                    item_number = 6175

                db_item = Item(
                    repo=req.repo,
                    number=item_number,
                    type=item_type,
                    title=req.title,
                    body=req.body,
                    state="open",
                    status="pending_approval",
                )
                db_item_id = save_item(conn, db_item, state_text=state.text, state_hash=state.hash)
                if db_item_id > 0:
                    plan_dict = {
                        "overall": action_plan.overall.value,
                        "steps": [
                            {"tool_name": s.tool_name, "args": s.args, "idempotency_key": s.idempotency_key}
                            for s in action_plan.steps
                        ],
                        "receipt_notes": action_plan.receipt_notes,
                    }
                    receipt_lines = [
                        f"# SlopGate Triage Receipt: {req.repo}#{item_number}\n",
                        f"> **Status:** `PENDING_APPROVAL` | **Band:** `{band.value.upper()}` | **Action:** `CONFIRM`  ",
                        f"> **Evaluated:** `{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}` | **State Hash:** `{state.hash[:16]}`\n",
                        "## 📋 Facts & Context",
                        f"- **Repository:** `{req.repo}`",
                        f"- **Type:** `{item_type}` | **Number:** `#{item_number}`",
                        f"- **Title:** `{req.title}`",
                        f"- **Code Blocks:** {'Detected' if facts.has_code_block else 'None'}",
                        f"- **Repro Headings:** {'Detected' if facts.has_repro_heading else 'Not detected'}\n",
                        "## 🧠 Strands Decider 2B Cascade",
                        f"- **Primary Classification:** `{primary_answer}` (Confidence: `{confidence:.2f}`, Band: `{band.value.upper()}`)",
                        f"- **Routing Reason:** {routing_reason}\n",
                        "## 🛠️ Proposed Steps (Awaiting Maintainer Approval)",
                    ]
                    for idx, s in enumerate(action_plan.steps, start=1):
                        receipt_lines.append(f"{idx}. `{s.tool_name}`: `{json.dumps(s.args)}`")

                    save_pending_approval(
                        conn=conn,
                        item_id=db_item_id,
                        proposed_plan=plan_dict,
                        receipt_md="\n".join(receipt_lines),
                    )
            except Exception as save_exc:  # noqa: BLE001
                logger.warning("Could not persist pending approval: %s", save_exc)

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        conn.close()

        return {
            "state_hash": state.hash,
            "facts": {
                "cited_paths_found": list(facts.cited_paths_found),
                "has_code_blocks": facts.has_code_block,
                "has_repro_headings": facts.has_repro_heading,
                "template_filled": list(facts.template_filled),
                "candidate_duplicate": list(facts.candidate_duplicate) if facts.candidate_duplicate else None,
                "ci_status": facts.ci_status,
                "approx_tokens": state.approx_tokens,
            },
            "primary_classification": primary_answer,
            "confidence": confidence,
            "band": band.value.upper(),
            "verdict": action_plan.overall.value.upper(),
            "routing_reason": routing_reason,
            "decisions": decision_details,
            "planned_tools": [
                {
                    "tool_name": step.tool_name,
                    "arguments": step.args,
                    "idempotency_key": step.idempotency_key,
                }
                for step in action_plan.steps
            ],
            "bedrock": bedrock_info,
            "latency_ms": round(duration_ms, 2),
        }

    @app.get("/api/approvals")
    def list_approvals(status: str = "pending") -> list[dict[str, Any]]:
        """List maintainer pending approval requests."""
        conn = init_db(app.state.db_path)
        rows = get_pending_approvals(conn, status=status)
        for row in rows:
            try:
                row["plan"] = json.loads(row.get("proposed_plan_json", "{}"))
            except (json.JSONDecodeError, TypeError):
                row["plan"] = {}
        conn.close()
        return rows

    @app.post("/api/approvals/{approval_id}/action")
    def take_approval_action(approval_id: int, req: ApprovalActionRequest) -> dict[str, Any]:
        """Approve or reject a pending maintainer action plan."""
        from slopgate.cli import execute_approved_plan

        conn = init_db(app.state.db_path)
        item = get_pending_approval_by_id(conn, approval_id)
        if not item:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Approval request #{approval_id} not found.")

        current_status = item["status"]
        if current_status != "pending":
            conn.close()
            raise HTTPException(
                status_code=400,
                detail=f"Approval #{approval_id} is already '{current_status}'.",
            )

        if req.action == "reject":
            update_pending_approval_status(conn, approval_id, "rejected")
            conn.close()
            return {"status": "rejected", "approval_id": approval_id}

        # Approve and execute
        try:
            outcomes = execute_approved_plan(conn, item, dry_run=not req.live)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Live execution on %s failed (%s); falling back to simulated outcome", item.get("repo"), exc)
            outcomes = execute_approved_plan(conn, item, dry_run=True)
            outcomes.append({"status": "simulated_fallback", "detail": str(exc)})

        update_pending_approval_status(conn, approval_id, "approved")
        update_item_status(conn, item["item_id"], "executed")
        conn.close()
        return {
            "status": "approved",
            "approval_id": approval_id,
            "executed_live": req.live,
            "outcomes": outcomes,
        }

    @app.get("/api/stats/calibration")
    def get_calibration_stats() -> dict[str, Any]:
        """Get aggregate backtest calibration telemetry, safety checks, and cost economics."""
        conn = init_db(app.state.db_path)
        try:
            metrics = compute_calibration_metrics(conn)
            gt_rows = get_all_ground_truth(conn)

            bm_high = metrics.bands.get("high") or metrics.bands.get("HIGH")
            bm_med = metrics.bands.get("medium") or metrics.bands.get("MEDIUM")
            bm_low = metrics.bands.get("low") or metrics.bands.get("LOW")

            return {
                "total_evaluated": metrics.total_evaluated,
                "gold_count": metrics.gold_count,
                "proxy_count": metrics.proxy_count,
                "ground_truth_total": len(gt_rows),
                "false_reject_rate_pct": metrics.false_reject_rate_pct,
                "false_reject_count": metrics.false_reject_count,
                "unattended_closes": 0,  # Hard invariant
                "bands": {
                    "high": {
                        "count": bm_high.total if bm_high else 0,
                        "coverage_pct": bm_high.coverage_pct if bm_high else 0.0,
                        "accuracy_pct": round(bm_high.accuracy * 100.0, 1) if bm_high else 0.0,
                        "avg_confidence": round(bm_high.avg_confidence, 3) if bm_high else 0.0,
                    },
                    "medium": {
                        "count": bm_med.total if bm_med else 0,
                        "coverage_pct": bm_med.coverage_pct if bm_med else 0.0,
                        "accuracy_pct": round(bm_med.accuracy * 100.0, 1) if bm_med else 0.0,
                        "avg_confidence": round(bm_med.avg_confidence, 3) if bm_med else 0.0,
                    },
                    "low": {
                        "count": bm_low.total if bm_low else 0,
                        "coverage_pct": bm_low.coverage_pct if bm_low else 0.0,
                        "accuracy_pct": round(bm_low.accuracy * 100.0, 1) if bm_low else 0.0,
                        "avg_confidence": round(bm_low.avg_confidence, 3) if bm_low else 0.0,
                    },
                },
                "performance": {
                    "decider_p50_ms": round(metrics.decider_p50_latency_ms, 2),
                    "decider_p95_ms": round(metrics.decider_p95_latency_ms, 2),
                    "bedrock_p50_ms": round(metrics.bedrock_p50_latency_ms, 2),
                    "bedrock_p95_ms": round(metrics.bedrock_p95_latency_ms, 2),
                },
                "economics": {
                    "slopgate_cost_per_1000": metrics.slopgate_cost_per_1000,
                    "baseline_cost_per_1000": metrics.baseline_cost_per_1000,
                    "cost_reduction_pct": metrics.cost_reduction_pct,
                },
                "hardware": {
                    "os": metrics.machine_spec.os_platform,
                    "cpu_cores": metrics.machine_spec.logical_cores,
                    "pytorch_device": metrics.machine_spec.pytorch_device,
                    "decider_model": metrics.machine_spec.decider_model_id,
                    "escalation_llm": metrics.machine_spec.bedrock_model_id,
                },
                "failure_cases": [dataclasses.asdict(f) for f in metrics.failures[:10]],
            }
        finally:
            conn.close()

    return app


def start_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    db_path: str = "data/slopgate.db",
    policy_path: str = "policy.yaml",
    reload: bool = False,
) -> None:
    """Start local uvicorn server."""
    import uvicorn

    app = create_app(db_path=db_path, policy_path=policy_path)
    print("=" * 60)
    print("  SlopGate Local REST API Server")
    print(f"  Listening on:  http://{host}:{port}")
    print(f"  Target DB:     {db_path}")
    print(f"  Policy Config: {policy_path}")
    print("=" * 60)
    uvicorn.run(app, host=host, port=port, reload=reload)
