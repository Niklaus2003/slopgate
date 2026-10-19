"""Unit tests for calibration metrics computation and Markdown report generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.models import ActionKind, Band, DeciderResult, GateVerdict, Item
from slopgate.report.calibration import (
    compute_calibration_metrics,
    export_calibration_report,
    get_machine_spec,
    render_markdown_calibration_report,
)
from slopgate.store.db import (
    init_db,
    save_decision,
    save_escalation,
    save_ground_truth,
    save_item,
)


def test_machine_spec_fields() -> None:
    spec = get_machine_spec()
    assert spec.logical_cores >= 1
    assert spec.configured_threads >= 1
    assert spec.decider_model_id != ""
    assert spec.pytorch_device.lower() in ("cpu", "cuda")


def test_calibration_metrics_and_markdown_generation(tmp_path: Path) -> None:
    db_file = tmp_path / "calib_test.db"
    conn = init_db(db_file)

    # Insert 3 items
    # Item 1: High band, correct
    it1 = Item(repo="p/f", number=1, type="issue", title="Valid bug report", body="repro")
    id1 = save_item(conn, it1)
    save_ground_truth(conn, id1, "real_bug_report", source="gold")
    d1 = DeciderResult(question_id="Q1", qtype="choice", answer="real_bug_report", probs={"real_bug_report": 0.95}, confidence=0.92, latency_ms=12.0)
    v1 = GateVerdict(question_id="Q1", band=Band.HIGH, action=ActionKind.PROCEED, reason="high conf bug")
    save_decision(conn, id1, d1, v1)

    # Item 2: Medium band, correct
    it2 = Item(repo="p/f", number=2, type="pull_request", title="Feature PR", body="code")
    id2 = save_item(conn, it2)
    save_ground_truth(conn, id2, "ready_for_review", source="proxy")
    d2 = DeciderResult(question_id="Q1", qtype="choice", answer="ready_for_review", probs={"ready_for_review": 0.70}, confidence=0.65, latency_ms=10.0)
    v2 = GateVerdict(question_id="Q1", band=Band.MEDIUM, action=ActionKind.CONFIRM, reason="medium conf PR")
    save_decision(conn, id2, d2, v2)

    # Item 3: Low band, incorrect prediction safely diverted
    it3 = Item(repo="p/f", number=3, type="issue", title="Short question", body="?")
    id3 = save_item(conn, it3)
    save_ground_truth(conn, id3, "support_question", source="proxy")
    d3 = DeciderResult(question_id="Q1", qtype="choice", answer="low_effort", probs={"low_effort": 0.40}, confidence=0.35, latency_ms=15.0)
    v3 = GateVerdict(question_id="Q1", band=Band.LOW, action=ActionKind.CONFIRM, reason="uncertain")
    save_decision(conn, id3, d3, v3)

    # Escalations
    save_escalation(
        conn,
        item_id=id2,
        purpose="baseline",
        bedrock_model="nova-micro",
        tokens_in=200,
        tokens_out=30,
        latency_ms=450.0,
        est_cost_usd=0.00005,
        output_text='{"label": "ready_for_review"}',
    )

    metrics = compute_calibration_metrics(conn)

    assert metrics.total_evaluated == 3
    assert metrics.gold_count == 1
    assert metrics.proxy_count == 2
    assert metrics.overall_accuracy == pytest.approx(2 / 3, rel=1e-2)
    assert metrics.false_reject_count == 0
    assert metrics.false_reject_rate_pct == 0.0

    # High band should have 1 item, 100% accuracy
    assert metrics.bands["high"].total == 1
    assert metrics.bands["high"].accuracy == 1.0

    # Failures list should contain item 3
    assert len(metrics.failures) == 1
    assert metrics.failures[0].number == 3
    assert metrics.failures[0].safely_diverted is True

    # Render Markdown report
    md = render_markdown_calibration_report(metrics)
    assert "# SlopGate — Model Calibration & Safety Backtest Report" in md
    assert "Hardware Profile & Benchmark Spec" in md
    assert "Calibration by Confidence Band" in md
    assert "False-Reject Rate on Accepted PRs/Issues" in md
    assert "0.0%" in md

    # Export report to disk
    report_file = tmp_path / "backtest.md"
    dest = export_calibration_report(metrics, report_file)
    assert dest.is_file()
    assert len(dest.read_text(encoding="utf-8")) > 500

    conn.close()
