"""SlopGate CLI interface."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from slopgate.agent.tools import (
    apply_label,
    close_item,
    flag_for_maintainer,
    post_comment,
    request_info_comment,
)
from slopgate.backtest import (
    load_gold_labels_from_csv,
    populate_proxy_ground_truth,
    run_backtest,
    run_bedrock_baseline,
    tune_thresholds,
)
from slopgate.bedrock.budget import BudgetGuard
from slopgate.bedrock.client import BedrockClient, MockBedrockClient
from slopgate.config import get_settings, load_policy
from slopgate.decider.client import FakeDecider
from slopgate.decider.in_process import InProcessDecider
from slopgate.ingest.github import GitHubClient
from slopgate.ingest.replay import (
    export_gold_candidates_csv,
    load_replay_items,
    save_replay_items,
    snapshot_repository,
)
from slopgate.report.calibration import (
    BandMetrics,
    compute_calibration_metrics,
    export_calibration_report,
)
from slopgate.report.receipts import (
    build_item_receipt,
    export_receipt_to_disk,
    render_markdown_receipt,
)
from slopgate.state.repo_index import RepoIndex
from slopgate.store.db import (
    get_all_item_ids,
    get_pending_approval_by_id,
    get_pending_approvals,
    init_db,
    save_item,
    update_item_status,
    update_pending_approval_status,
)
from slopgate.worker import Worker


def check_version(pkg_name: str) -> str:
    """Return version string or NOT INSTALLED."""
    try:
        return version(pkg_name)
    except PackageNotFoundError:
        return "NOT INSTALLED"


def run_doctor() -> int:
    """Execute the doctor command to verify environment integrity."""
    settings = get_settings()
    python_exe = sys.executable
    is_venv = ".venv" in python_exe or hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    )

    print("=" * 60)
    print("  SlopGate Doctor — System & Environment Check")
    print("=" * 60)

    # 1. Python & Venv
    print("\n[Python Environment]")
    print(f"  Python Version:     {platform.python_version()}")
    print(f"  Executable Path:    {python_exe}")
    print(f"  Virtual Env Active: {'YES (Isolated)' if is_venv else 'NO (Warning: Global Python!)'}")

    # 2. System Hardware
    print("\n[Hardware Profile]")
    print(f"  OS Platform:        {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"  Logical CPU Cores:  {os.cpu_count() or 'Unknown'}")
    print(f"  Configured Threads: {settings.decider_threads}")

    # 3. Environment Variables & Credentials (SAFE: values never leaked)
    print("\n[Configuration & Credentials]")
    for key, status in settings.doctor_summary().items():
        print(f"  {key:<28} {status}")

    # 4. Critical Dependencies
    print("\n[Dependency Status]")
    packages = [
        "torch",
        "strands-decider",
        "boto3",
        "pydantic",
        "pyyaml",
        "httpx",
        "scikit-learn",
        "rank-bm25",
        "pytest",
    ]
    for pkg in packages:
        status = check_version(pkg)
        indicator = "OK" if status != "NOT INSTALLED" else "MISSING"
        print(f"  {pkg:<20} {status:<18} [{indicator}]")

    print("\n" + "=" * 60)
    return 0


def run_ingest(args: argparse.Namespace) -> int:
    """Execute item ingestion from GitHub or offline replay."""
    policy = load_policy()
    repo = args.repo or policy.repo or "pallets/flask"
    limit = args.limit
    db_path = args.db or "data/slopgate.db"

    print("=" * 60)
    print(f"  SlopGate Ingestion — Target: {repo}")
    print("=" * 60)

    items = []
    if args.replay:
        print(f"\n[Replay Mode] Loading snapshot from {args.replay}...")
        items = load_replay_items(args.replay)
        print(f"  Loaded {len(items)} items from offline snapshot.")
    else:
        print(f"\n[Live API Mode] Fetching up to {limit} issues/PRs from GitHub...")
        if args.save and args.tree:
            print("  Snapshotting repo data and file tree...")
            n_items, n_files = snapshot_repository(
                repo=repo,
                output_items_path=args.save,
                output_tree_path=args.tree,
                limit=limit,
            )
            print(f"  Saved {n_items} items -> {args.save}")
            print(f"  Saved {n_files} tree files -> {args.tree}")
            items = load_replay_items(args.save)
        else:
            client = GitHubClient()
            items, _ = client.fetch_issues(repo=repo, limit=limit)
            print(f"  Fetched {len(items)} items from {repo}.")
            if args.save:
                save_replay_items(items, args.save)
                print(f"  Saved {len(items)} items -> {args.save}")

    # Export gold labeling candidates if requested
    if args.export_gold:
        n_gold = export_gold_candidates_csv(items, args.export_gold, limit=60)
        print(f"  Exported {n_gold} candidates for gold labeling -> {args.export_gold}")

    # Persist items to local SQLite queue
    print(f"\n[Database Persistence] Syncing into {db_path}...")
    conn = init_db(db_path)
    saved_count = 0
    for item in items:
        save_item(conn, item)
        saved_count += 1
    conn.close()

    print(f"  Successfully queued {saved_count} items into SQLite.")
    print("\n" + "=" * 60)
    return 0


def execute_approved_plan(
    conn: Any,
    approval: dict[str, Any],
    dry_run: bool = True,
) -> list[dict[str, Any]]:
    """Execute tools in an approved plan. This is the ONLY authorized path for close_item."""
    plan_data = json.loads(approval["proposed_plan_json"])
    item_id = approval["item_id"]
    repo = approval["repo"]
    number = approval["number"]

    outcomes: list[dict[str, Any]] = []
    for step in plan_data.get("steps", []):
        tool_name = step.get("tool_name")
        args = step.get("args", {})
        if tool_name == "close_item":
            res = close_item(
                repo=repo,
                number=number,
                reason=args.get("reason", "Closed via maintainer approval"),
                dry_run=dry_run,
                conn=conn,
                item_id=item_id,
            )
            outcomes.append(res)
        elif tool_name == "apply_label":
            res = apply_label(
                repo=repo,
                number=number,
                label=args["label"],
                dry_run=dry_run,
                conn=conn,
                item_id=item_id,
            )
            outcomes.append(res)
        elif tool_name == "post_comment":
            res = post_comment(
                repo=repo,
                number=number,
                body=args["body"],
                dry_run=dry_run,
                conn=conn,
                item_id=item_id,
            )
            outcomes.append(res)
        elif tool_name == "request_info_comment":
            res = request_info_comment(
                repo=repo,
                number=number,
                template_type=args.get("template_type", "general"),
                missing_fields=args.get("missing_fields"),
                dry_run=dry_run,
                conn=conn,
                item_id=item_id,
            )
            outcomes.append(res)
        elif tool_name == "flag_for_maintainer":
            res = flag_for_maintainer(
                repo=repo,
                number=number,
                reason=args.get("reason", "Maintainer review"),
                suggested_action=args.get("suggested_action", "review"),
                dry_run=dry_run,
                conn=conn,
                item_id=item_id,
            )
            outcomes.append(res)
    return outcomes


def run_review(args: argparse.Namespace) -> int:
    """Execute maintainer review inbox actions."""
    db_path = getattr(args, "db", "data/slopgate.db")
    conn = init_db(db_path)
    action = getattr(args, "review_action", "list") or "list"

    print("=" * 60)
    print("  SlopGate Maintainer Review Inbox")
    print("=" * 60)

    if action == "list":
        status_filter = getattr(args, "status", "pending") or "pending"
        pending = get_pending_approvals(conn, status=status_filter)
        print(f"\n[Pending Approvals (Status: {status_filter})] Total: {len(pending)}")
        if not pending:
            print("  No pending approval items found.")
            conn.close()
            print("\n" + "=" * 60)
            return 0

        print(f"  {'ID':<5} {'Target':<24} {'Type':<12} {'Status':<10} {'Title'}")
        print("  " + "-" * 55)
        for p in pending:
            target = f"{p['repo']}#{p['number']}"
            title = (p.get("title") or "")[:30]
            print(f"  {p['id']:<5} {target:<24} {p['type']:<12} {p['status']:<10} {title}")
        conn.close()
        print("\n" + "=" * 60)
        return 0

    if action == "show":
        approval_id = getattr(args, "id", None)
        if not approval_id:
            print("Error: Missing approval ID. Usage: slopgate review show <id>")
            conn.close()
            return 1
        item = get_pending_approval_by_id(conn, approval_id)
        if not item:
            print(f"Error: Pending approval with ID {approval_id} not found.")
            conn.close()
            return 1

        print(f"\nApproval Request ID: #{item['id']}")
        print(f"Target Item:         {item['repo']}#{item['number']} ({item['type']})")
        print(f"Title:               {item.get('title')}")
        print(f"Current Status:      {item['status']}")
        if item.get("receipt_md"):
            print(f"\nReceipt Notes:\n{item['receipt_md']}")
        print(f"\nProposed Action Plan:\n{item['proposed_plan_json']}")
        conn.close()
        print("\n" + "=" * 60)
        return 0

    if action == "approve":
        approval_id = getattr(args, "id", None)
        live = getattr(args, "live", False)
        if not approval_id:
            print("Error: Missing approval ID. Usage: slopgate review approve <id> [--live]")
            conn.close()
            return 1
        item = get_pending_approval_by_id(conn, approval_id)
        if not item:
            print(f"Error: Pending approval with ID {approval_id} not found.")
            conn.close()
            return 1
        if item["status"] != "pending":
            print(f"Warning: Approval #{approval_id} is already '{item['status']}'.")
            conn.close()
            return 0

        print(f"\n[APPROVED] Executing action plan for {item['repo']}#{item['number']} (Live: {live})...")
        outcomes = execute_approved_plan(conn, item, dry_run=not live)
        update_pending_approval_status(conn, approval_id, "approved")
        update_item_status(conn, item["item_id"], "executed")
        conn.close()
        for out in outcomes:
            print(f"  - Action {out.get('tool')}: status={out.get('status')}")
        print("\nApproval executed successfully.")
        print("=" * 60)
        return 0

    if action == "reject":
        approval_id = getattr(args, "id", None)
        if not approval_id:
            print("Error: Missing approval ID. Usage: slopgate review reject <id>")
            conn.close()
            return 1
        item = get_pending_approval_by_id(conn, approval_id)
        if not item:
            print(f"Error: Pending approval with ID {approval_id} not found.")
            conn.close()
            return 1
        update_pending_approval_status(conn, approval_id, "rejected")
        update_item_status(conn, item["item_id"], "dismissed")
        conn.close()
        print(f"\n[REJECTED] Action plan for {item['repo']}#{item['number']} has been rejected and dismissed.")
        print("=" * 60)
        return 0

    conn.close()
    return 0


def run_worker_cli(args: argparse.Namespace) -> int:
    """Execute background worker draining the queue."""
    db_path = getattr(args, "db", "data/slopgate.db")
    limit = getattr(args, "limit", None)
    policy_path = getattr(args, "policy", "policy.yaml")
    tree_path = getattr(args, "tree", None)
    decider_type = getattr(args, "decider", "in_process")
    use_mock_bedrock = getattr(args, "mock_bedrock", False)
    live = getattr(args, "live", False)

    policy = load_policy(policy_path)
    conn = init_db(db_path)

    repo_index = None
    if tree_path and Path(tree_path).is_file():
        tree_files = json.loads(Path(tree_path).read_text(encoding="utf-8"))
        repo_index = RepoIndex.from_file_list(tree_files)

    if decider_type == "fake":
        decider = FakeDecider()
    else:
        decider = InProcessDecider(conn=conn)

    if use_mock_bedrock:
        bedrock_client = MockBedrockClient()
    else:
        bedrock_client = BedrockClient()

    budget = BudgetGuard()

    print("=" * 60)
    print("  SlopGate Background Triage Worker")
    print(f"  Target DB:     {db_path}")
    print(f"  Policy:        {policy_path} (repo: {policy.repo})")
    print(f"  Decider:       {decider_type}")
    print(f"  Execution:     {'LIVE MUTATIONS' if live else 'DRY-RUN (Safe)'}")
    print(f"  Queue Limit:   {limit or 'All pending items'}")
    print("=" * 60)

    def on_progress(p: dict[str, Any]):
        print(f"  [{p['completed']}] {p['repo']}#{p['number']} -> {p['status'].upper()}")

    worker = Worker(
        conn=conn,
        policy=policy,
        decider=decider,
        bedrock_client=bedrock_client,
        budget=budget,
        repo_index=repo_index,
        dry_run=not live,
        on_progress=on_progress,
    )

    summary = worker.run(limit=limit)
    print("\n" + summary.format_console_report())
    conn.close()
    return 0 if summary.errors == 0 else 1


def run_report_cli(args: argparse.Namespace) -> int:
    """Generate and display or save receipts."""
    db_path = getattr(args, "db", "data/slopgate.db")
    item_id = getattr(args, "item", None)
    all_items = getattr(args, "all", False)
    output_dir = getattr(args, "output", None)
    as_json = getattr(args, "json", False)

    conn = init_db(db_path)

    if item_id:
        try:
            receipt = build_item_receipt(conn, item_id)
            if output_dir:
                path = export_receipt_to_disk(receipt, output_dir=output_dir, as_markdown=not as_json)
                print(f"Saved receipt for item #{item_id} -> {path}")
            elif as_json:
                print(json.dumps(receipt, indent=2))
            else:
                print(render_markdown_receipt(receipt))
        except ValueError as err:
            print(f"Error: {err}")
            conn.close()
            return 1
    elif all_items:
        item_ids = get_all_item_ids(conn)
        out_dir = output_dir or "reports/receipts"
        count = 0
        for iid in item_ids:
            try:
                receipt = build_item_receipt(conn, iid)
                export_receipt_to_disk(receipt, output_dir=out_dir, as_markdown=not as_json)
                count += 1
            except Exception as err:  # noqa: BLE001
                print(f"Warning: Failed to render receipt for item #{iid}: {err}")
        print(f"Successfully exported {count} receipts to {out_dir}/")
    else:
        print("Please specify an item ID (--item <id>) or export all (--all).")
        conn.close()
        return 1

    conn.close()
    return 0


def run_demo_cli(args: argparse.Namespace) -> int:
    """Run an end-to-end dry-run demo showcase."""
    print("=" * 60)
    print("  SlopGate End-to-End Showcase Demo")
    print("=" * 60)

    db_path = getattr(args, "db", "data/demo.db")
    limit = getattr(args, "limit", 5)

    samples_path = Path("data/samples/flask.json")
    tree_path = Path("data/samples/flask_tree.json")
    policy_path = Path("policy.yaml") if Path("policy.yaml").is_file() else Path("policy.example.yaml")

    if not samples_path.is_file():
        print(f"Error: Demo sample data not found at {samples_path}. Run 'slopgate ingest' first.")
        return 1

    # 1. Ingest demo items into isolated demo DB
    conn = init_db(db_path)
    items = load_replay_items(samples_path)[:limit]
    for it in items:
        save_item(conn, it)
    print(f"\n[1/3] Seeded {len(items)} items into demo database ({db_path})")

    # 2. Run Worker in dry-run mode with MockBedrockClient
    repo_index = None
    if tree_path.is_file():
        tree_files = json.loads(tree_path.read_text(encoding="utf-8"))
        repo_index = RepoIndex.from_file_list(tree_files)

    policy = load_policy(policy_path)
    decider = FakeDecider()
    bedrock = MockBedrockClient()

    print(f"\n[2/3] Running triage worker (Dry-Run: ON, Policy: {policy.repo})...")

    def on_progress(p: dict[str, Any]):
        print(f"  - Item {p['repo']}#{p['number']}: {p['status'].upper()}")

    worker = Worker(
        conn=conn,
        policy=policy,
        decider=decider,
        bedrock_client=bedrock,
        repo_index=repo_index,
        dry_run=True,
        on_progress=on_progress,
    )
    summary = worker.run()

    print("\n" + summary.format_console_report())

    # 3. Export receipts and display Review Inbox status
    receipts_dir = Path("reports/demo_receipts")
    for row in conn.execute("SELECT id FROM items").fetchall():
        receipt = build_item_receipt(conn, row["id"])
        export_receipt_to_disk(receipt, output_dir=receipts_dir, as_markdown=True)
    print(f"\n[3/3] Exported demo receipts -> {receipts_dir}/")

    pending = conn.execute("SELECT COUNT(*) as cnt FROM pending_approvals WHERE status = 'pending'").fetchone()
    pending_cnt = pending["cnt"] if pending else 0
    print(f"\nMaintainer Review Inbox: {pending_cnt} pending approval requests.")
    print("Run 'slopgate review list --db data/demo.db' to inspect and approve.")
    print("=" * 60)
    conn.close()
    return 0


def run_backtest_cli(args: argparse.Namespace) -> int:
    """Execute offline calibration backtest, threshold tuning, or ground truth loading."""
    db_path = getattr(args, "db", "data/slopgate.db")
    conn = init_db(db_path)
    policy_path = getattr(args, "policy", "policy.yaml")
    policy = load_policy(policy_path)

    action = getattr(args, "backtest_action", None)

    # 1. Load gold labels command
    if action == "load-gold":
        csv_path = getattr(args, "csv", None) or getattr(args, "csv_pos", None)
        if not csv_path:
            print("Error: CSV path must be provided via argument or --csv.")
            conn.close()
            return 1
        loaded = load_gold_labels_from_csv(conn, csv_path)
        print(f"Loaded {loaded} human gold labels from {csv_path} into {db_path}.")
        conn.close()
        return 0

    # 2. Threshold tuning command
    if action == "tune":
        query = """
            SELECT d.answer as predicted, d.confidence, g.label as actual, i.type as item_type
            FROM decisions d
            JOIN items i ON d.item_id = i.id
            JOIN ground_truth g ON d.item_id = g.item_id
            WHERE d.question_id = 'Q1'
            ORDER BY i.id ASC
        """
        rows = [dict(r) for r in conn.execute(query).fetchall()]
        if not rows:
            print("No evaluated items with ground truth found in database. Run 'slopgate backtest run' first.")
            conn.close()
            return 1

        tuning = tune_thresholds(
            rows,
            current_high=policy.bands.choice.high_at_least,
            current_medium=policy.bands.choice.medium_at_least,
        )
        print("=" * 60)
        print("  SlopGate Policy Threshold Tuning Optimizer")
        print("=" * 60)
        print(f"Evaluated Items:        {len(rows)} (Train 70% / Held-Out 30%)")
        print(f"Current Thresholds:     High: {tuning.current_high:.2f} | Medium: {tuning.current_medium:.2f}")
        print(f"Current Held-Out Acc:   {tuning.current_heldout_acc * 100:.1f}% (Coverage: {tuning.current_heldout_coverage:.1f}%)")
        print(f"Recommended Thresholds: High: {tuning.recommended_high:.2f} | Medium: {tuning.recommended_medium:.2f}")
        print(f"Recommended Held-Out:   {tuning.recommended_heldout_acc * 100:.1f}% (Coverage: {tuning.recommended_heldout_coverage:.1f}%)")
        print(f"Status:                 {'[RETAINED] Default Policy Verified' if tuning.retained_current else '[UPDATED] Tuned Thresholds Available'}")
        print(f"Rationale:              {tuning.rationale}")
        print("=" * 60)
        conn.close()
        return 0

    # 3. Default: Run backtest
    replay_path = getattr(args, "replay", "data/samples/flask.json")
    print("=" * 60)
    print("  SlopGate Offline Calibration Backtest")
    print("=" * 60)

    # Load items
    items = load_replay_items(replay_path)
    limit = getattr(args, "limit", None)
    if limit and limit > 0:
        items = items[:limit]
    print(f"\n[1/5] Loaded {len(items)} items from {replay_path}")

    # Populate proxy ground truth
    populated = populate_proxy_ground_truth(conn, items)
    print(f"[2/5] Initialized ground truth ({populated} proxy outcome labels mapped)")

    # Optional load gold labels
    gold_csv = getattr(args, "load_gold", None)
    if gold_csv and Path(gold_csv).is_file():
        loaded_gold = load_gold_labels_from_csv(conn, gold_csv)
        print(f"      Loaded {loaded_gold} gold labels from {gold_csv}")

    # Setup decider & repo tree index
    tree_path = getattr(args, "tree", "data/samples/flask_tree.json")
    repo_index = RepoIndex.from_json(tree_path) if Path(tree_path).is_file() else None

    decider_kind = getattr(args, "decider", "in_process")
    if decider_kind == "fake":
        decider = FakeDecider()
    else:
        decider = InProcessDecider()

    print(f"[3/5] Running Decider inference on CPU (Backend: {decider_kind})...")
    bt_res = run_backtest(
        items=items,
        conn=conn,
        policy=policy,
        decider=decider,
        repo_index=repo_index,
    )
    print(f"      Completed {bt_res.total_items} items in {bt_res.duration_seconds:.2f}s ({bt_res.total_decisions} decisions, {bt_res.cache_hits} cache hits)")

    # Optional Bedrock baseline
    if getattr(args, "run_baseline", False):
        print("\n[4/5] Running Bedrock classification baseline...")
        if getattr(args, "mock_bedrock", False):
            bedrock_client = MockBedrockClient()
        else:
            bedrock_client = BedrockClient()
        budget_guard = BudgetGuard(max_calls=25, max_cost_usd=1.0)
        baseline_res = run_bedrock_baseline(
            items=items,
            conn=conn,
            bedrock_client=bedrock_client,
            budget_guard=budget_guard,
            limit=min(len(items), 20),
        )
        print(f"      Baseline evaluated {baseline_res.total_items} items (${baseline_res.total_cost_usd:.5f} total cost, avg {baseline_res.accuracy*100:.1f}% accuracy)")
    else:
        print("\n[4/5] Skipping live Bedrock baseline (use --run-baseline to execute)")

    # Compute calibration metrics and export report
    metrics = compute_calibration_metrics(conn)
    report_path = getattr(args, "report", "reports/backtest.md")
    dest = export_calibration_report(metrics, report_path)
    print(f"\n[5/5] Exported calibration report -> {dest}")

    # Console summary
    bm_high = metrics.bands.get("high", BandMetrics("HIGH"))
    bm_med = metrics.bands.get("medium", BandMetrics("MEDIUM"))
    bm_low = metrics.bands.get("low", BandMetrics("LOW"))
    print("\n" + "=" * 60)
    print("  Calibration Summary")
    print("=" * 60)
    print(f"Evaluated Items:    {metrics.total_evaluated} ({metrics.gold_count} Gold / {metrics.proxy_count} Proxy)")
    print(f"Accuracy by Band:   HIGH: {bm_high.accuracy*100:.1f}% ({bm_high.coverage_pct:.1f}% cov) | MED: {bm_med.accuracy*100:.1f}% | LOW: {bm_low.accuracy*100:.1f}%")
    print(f"False-Reject Rate:  {metrics.false_reject_rate_pct:.1f}% ({metrics.false_reject_count} errors on legitimate items) [Target: 0.0%]")
    print(f"Decider Latency:    p50: {metrics.decider_p50_latency_ms:.2f} ms | p95: {metrics.decider_p95_latency_ms:.2f} ms")
    print(f"Cost Economics:     SlopGate: ${metrics.slopgate_cost_per_1000:.4f}/1k vs Baseline: ${metrics.baseline_cost_per_1000:.4f}/1k ({metrics.cost_reduction_pct:.1f}% savings)")
    print("=" * 60)

    conn.close()
    return 0


def run_serve_cli(args: argparse.Namespace) -> int:
    """Execute local REST API server."""
    from slopgate.api.server import start_server

    port = getattr(args, "port", 8000)
    host = getattr(args, "host", "127.0.0.1")
    db_path = getattr(args, "db", "data/slopgate.db")
    policy_path = getattr(args, "policy", "policy.yaml")
    reload = getattr(args, "reload", False)

    start_server(host=host, port=port, db_path=db_path, policy_path=policy_path, reload=reload)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="slopgate",
        description="SlopGate: Local, confidence-gated issue and PR triage.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # doctor command
    subparsers.add_parser("doctor", help="Inspect environment, dependencies, and settings")

    # ingest command
    ingest_parser = subparsers.add_parser("ingest", help="Ingest issues/PRs from GitHub or saved replay")
    ingest_parser.add_argument("--repo", type=str, default=None, help="Target repository (e.g. pallets/flask)")
    ingest_parser.add_argument("--limit", type=int, default=50, help="Maximum number of items to fetch (default: 50)")
    ingest_parser.add_argument("--replay", type=str, default=None, help="Path to offline replay JSON snapshot")
    ingest_parser.add_argument("--save", type=str, default=None, help="Save fetched items to JSON snapshot path")
    ingest_parser.add_argument("--tree", type=str, default=None, help="Save repo file tree to JSON path")
    ingest_parser.add_argument("--export-gold", type=str, default=None, help="Export gold candidate CSV")
    ingest_parser.add_argument("--db", type=str, default="data/slopgate.db", help="Target SQLite DB path")

    # review command
    review_parser = subparsers.add_parser("review", help="Review and approve pending actions")
    review_sub = review_parser.add_subparsers(dest="review_action", help="Review actions")

    list_p = review_sub.add_parser("list", help="List pending approvals")
    list_p.add_argument("--status", type=str, default="pending", help="Filter by status (pending|approved|rejected)")
    list_p.add_argument("--db", type=str, default="data/slopgate.db", help="Target SQLite DB path")

    show_p = review_sub.add_parser("show", help="Show details of a pending approval")
    show_p.add_argument("id", type=int, help="Approval ID")
    show_p.add_argument("--db", type=str, default="data/slopgate.db", help="Target SQLite DB path")

    approve_p = review_sub.add_parser("approve", help="Approve and execute a pending action plan")
    approve_p.add_argument("id", type=int, help="Approval ID")
    approve_p.add_argument("--live", action="store_true", default=False, help="Execute live writes on GitHub")
    approve_p.add_argument("--db", type=str, default="data/slopgate.db", help="Target SQLite DB path")

    reject_p = review_sub.add_parser("reject", help="Reject and dismiss a pending action plan")
    reject_p.add_argument("id", type=int, help="Approval ID")
    reject_p.add_argument("--db", type=str, default="data/slopgate.db", help="Target SQLite DB path")

    # run command
    run_parser = subparsers.add_parser("run", help="Run background triage worker")
    run_parser.add_argument("--limit", type=int, default=None, help="Maximum number of items to process")
    run_parser.add_argument("--db", type=str, default="data/slopgate.db", help="Target SQLite DB path")
    run_parser.add_argument("--policy", type=str, default="policy.yaml", help="Path to policy YAML")
    run_parser.add_argument("--tree", type=str, default=None, help="Path to repository file tree JSON")
    run_parser.add_argument(
        "--decider",
        type=str,
        default="in_process",
        choices=["in_process", "fake"],
        help="Decider backend to use",
    )
    run_parser.add_argument("--mock-bedrock", action="store_true", default=False, help="Use MockBedrockClient")
    run_parser.add_argument("--live", action="store_true", default=False, help="Execute live writes")

    # report command
    report_parser = subparsers.add_parser("report", help="Generate receipts and calibration report")
    report_parser.add_argument("--item", type=int, default=None, help="Item integer ID to generate receipt for")
    report_parser.add_argument("--all", action="store_true", default=False, help="Export receipts for all items")
    report_parser.add_argument("--db", type=str, default="data/slopgate.db", help="Target SQLite DB path")
    report_parser.add_argument("--output", type=str, default=None, help="Directory to save exported receipts")
    report_parser.add_argument("--json", action="store_true", default=False, help="Output JSON instead of Markdown")

    # demo command
    demo_parser = subparsers.add_parser("demo", help="Run end-to-end dry-run demo showcase")
    demo_parser.add_argument("--limit", type=int, default=5, help="Number of demo items to process")
    demo_parser.add_argument("--db", type=str, default="data/demo.db", help="Demo SQLite DB path")

    # backtest command
    backtest_parser = subparsers.add_parser("backtest", help="Run offline calibration backtest and tuning")
    backtest_sub = backtest_parser.add_subparsers(dest="backtest_action", help="Backtest actions")

    bt_run = backtest_sub.add_parser("run", help="Run offline decision backtest")
    bt_run.add_argument("--replay", type=str, default="data/samples/flask.json", help="Path to offline replay JSON")
    bt_run.add_argument("--tree", type=str, default="data/samples/flask_tree.json", help="Path to repo tree JSON")
    bt_run.add_argument("--db", type=str, default="data/slopgate.db", help="Target SQLite DB path")
    bt_run.add_argument("--policy", type=str, default="policy.yaml", help="Path to policy YAML")
    bt_run.add_argument("--limit", type=int, default=None, help="Maximum number of items to evaluate")
    bt_run.add_argument("--decider", type=str, default="in_process", choices=["in_process", "fake"], help="Decider backend")
    bt_run.add_argument("--run-baseline", action="store_true", default=False, help="Run Bedrock baseline comparison")
    bt_run.add_argument("--mock-bedrock", action="store_true", default=False, help="Use MockBedrockClient for baseline")
    bt_run.add_argument("--report", type=str, default="reports/backtest.md", help="Output path for calibration report")
    bt_run.add_argument("--load-gold", type=str, default=None, help="Path to gold labels CSV to load")

    bt_gold = backtest_sub.add_parser("load-gold", help="Load human gold labels from CSV")
    bt_gold.add_argument("csv_pos", nargs="?", default=None, help="Path to labeled CSV file")
    bt_gold.add_argument("--csv", type=str, default=None, help="Path to labeled CSV file")
    bt_gold.add_argument("--db", type=str, default="data/slopgate.db", help="Target SQLite DB path")

    bt_tune = backtest_sub.add_parser("tune", help="Optimize policy thresholds on train/held-out split")
    bt_tune.add_argument("--db", type=str, default="data/slopgate.db", help="Target SQLite DB path")
    bt_tune.add_argument("--policy", type=str, default="policy.yaml", help="Path to policy YAML")

    # serve command
    serve_parser = subparsers.add_parser("serve", help="Run local REST API server for Next.js dashboard")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    serve_parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    serve_parser.add_argument("--db", type=str, default="data/slopgate.db", help="Target SQLite DB path")
    serve_parser.add_argument("--policy", type=str, default="policy.yaml", help="Path to policy YAML")
    serve_parser.add_argument("--reload", action="store_true", default=False, help="Enable auto-reload for dev")

    args = parser.parse_args(argv)

    if args.command == "doctor" or args.command is None:
        return run_doctor()
    if args.command == "ingest":
        return run_ingest(args)
    if args.command == "review":
        return run_review(args)
    if args.command == "run":
        return run_worker_cli(args)
    if args.command == "report":
        return run_report_cli(args)
    if args.command == "demo":
        return run_demo_cli(args)
    if args.command == "backtest":
        return run_backtest_cli(args)
    if args.command == "serve":
        return run_serve_cli(args)

    print(f"Command '{args.command}' will be available in its respective implementation phase.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
