"""Dry-run aware, idempotent agent tools for GitHub actions.

Implements the five core triage actions:
1. apply_label: Tag item with maintainer labels
2. post_comment: Send feedback or guidance comment
3. request_info_comment: Polite template-driven request for missing details
4. flag_for_maintainer: Queue internal audit flag for maintainer attention
5. close_item: Close issue/PR (strictly gated, never auto-executed without approval)

Follows: architecture.md §6.6, docs/defense/02_CONSTRAINTS.md.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from typing import Any

from strands import tool

from slopgate.config import get_settings
from slopgate.ingest.github import GitHubClient
from slopgate.store.db import has_action_been_executed, save_action

logger = logging.getLogger(__name__)


def compute_idempotency_key(tool_name: str, repo: str, number: int, args: dict[str, Any]) -> str:
    """Compute a deterministic, collision-resistant idempotency key for an action."""
    repo_clean = repo.strip().lower()
    if tool_name == "apply_label":
        label_clean = str(args.get("label", "")).strip().lower()
        return f"{repo_clean}#{number}:label:{label_clean}"

    if tool_name == "post_comment":
        body_text = str(args.get("body", "")).strip()
        body_hash = hashlib.sha256(body_text.encode("utf-8")).hexdigest()[:16]
        return f"{repo_clean}#{number}:comment:{body_hash}"

    if tool_name == "request_info_comment":
        tmpl = str(args.get("template_type", "general")).strip().lower()
        fields = sorted(str(f).strip().lower() for f in args.get("missing_fields", []))
        fields_str = ",".join(fields)
        fields_hash = hashlib.sha256(fields_str.encode("utf-8")).hexdigest()[:12]
        return f"{repo_clean}#{number}:req_info:{tmpl}:{fields_hash}"

    if tool_name == "flag_for_maintainer":
        reason = str(args.get("reason", "")).strip().lower()
        reason_hash = hashlib.sha256(reason.encode("utf-8")).hexdigest()[:16]
        return f"{repo_clean}#{number}:flag:{reason_hash}"

    if tool_name == "close_item":
        reason = str(args.get("reason", "")).strip().lower()
        reason_hash = hashlib.sha256(reason.encode("utf-8")).hexdigest()[:16]
        return f"{repo_clean}#{number}:close:{reason_hash}"

    # Fallback for generic or unlisted tools
    args_json = json.dumps(args, sort_keys=True)
    args_hash = hashlib.sha256(args_json.encode("utf-8")).hexdigest()[:16]
    return f"{repo_clean}#{number}:{tool_name}:{args_hash}"


def _build_info_request_comment(
    template_type: str = "general",
    missing_fields: list[str] | None = None,
) -> str:
    """Build a kind, constructive request for missing information.

    Invariants:
    - Never accuses contributor of AI authorship or low effort.
    - Specifies precisely what is missing (reproduction steps, version, minimal example).
    """
    missing_fields = missing_fields or []
    bullet_points = "\n".join(f"- **{field}**" for field in missing_fields) or "- Additional context or reproduction details"

    if template_type == "reproduction":
        return (
            "Thanks for reporting this issue! To help the maintainers investigate and fix the problem, "
            "could you please provide the following details?\n\n"
            f"{bullet_points}\n\n"
            "A minimal code snippet or step-by-step example where this occurs would be especially helpful. Thank you!"
        )

    if template_type == "environment":
        return (
            "Thank you for contributing! Could you please share more details about your environment so we can replicate this?\n\n"
            f"{bullet_points}\n\n"
            "Include your OS version, Python version, and relevant library versions. Thank you!"
        )

    return (
        "Thanks for opening this issue! We'd love to help, but need a bit more information:\n\n"
        f"{bullet_points}\n\n"
        "Once provided, we'll be happy to take a closer look."
    )


# ---------------------------------------------------------------------------
# Direct Python Implementations
# ---------------------------------------------------------------------------


def apply_label(
    repo: str,
    number: int,
    label: str,
    dry_run: bool | None = None,
    conn: sqlite3.Connection | None = None,
    item_id: int | None = None,
    github_client: GitHubClient | None = None,
) -> dict[str, Any]:
    """Apply a label to an issue or pull request."""
    if dry_run is None:
        dry_run = get_settings().dry_run

    args = {"label": label}
    key = compute_idempotency_key("apply_label", repo, number, args)

    if conn and has_action_been_executed(conn, key):
        logger.info("Skipping duplicate action: %s", key)
        return {
            "status": "skipped",
            "tool": "apply_label",
            "reason": "Duplicate idempotency key match",
            "idempotency_key": key,
            "args": args,
        }

    if dry_run:
        logger.info("[DRY-RUN] apply_label: %s#%d -> %s", repo, number, label)
        if conn and item_id and item_id > 0:
            save_action(
                conn=conn,
                item_id=item_id,
                tool="apply_label",
                args=args,
                handler_result="proceed",
                dry_run=True,
                idempotency_key=key,
            )
        return {
            "status": "simulated",
            "tool": "apply_label",
            "dry_run": True,
            "idempotency_key": key,
            "args": args,
        }

    # Live execution
    client = github_client or GitHubClient(token=get_settings().github_write_token or get_settings().github_token)
    applied = client.add_labels(repo, number, [label])
    if conn and item_id and item_id > 0:
        save_action(
            conn=conn,
            item_id=item_id,
            tool="apply_label",
            args=args,
            handler_result="proceed",
            dry_run=False,
            idempotency_key=key,
        )
    return {
        "status": "executed",
        "tool": "apply_label",
        "dry_run": False,
        "idempotency_key": key,
        "applied_labels": applied,
        "args": args,
    }


def post_comment(
    repo: str,
    number: int,
    body: str,
    dry_run: bool | None = None,
    conn: sqlite3.Connection | None = None,
    item_id: int | None = None,
    github_client: GitHubClient | None = None,
) -> dict[str, Any]:
    """Post a markdown comment on an issue or pull request."""
    if dry_run is None:
        dry_run = get_settings().dry_run

    args = {"body": body}
    key = compute_idempotency_key("post_comment", repo, number, args)

    if conn and has_action_been_executed(conn, key):
        logger.info("Skipping duplicate action: %s", key)
        return {
            "status": "skipped",
            "tool": "post_comment",
            "reason": "Duplicate idempotency key match",
            "idempotency_key": key,
            "args": args,
        }

    if dry_run:
        logger.info("[DRY-RUN] post_comment: %s#%d -> %s chars", repo, number, len(body))
        if conn and item_id and item_id > 0:
            save_action(
                conn=conn,
                item_id=item_id,
                tool="post_comment",
                args=args,
                handler_result="proceed",
                dry_run=True,
                idempotency_key=key,
            )
        return {
            "status": "simulated",
            "tool": "post_comment",
            "dry_run": True,
            "idempotency_key": key,
            "args": args,
        }

    client = github_client or GitHubClient(token=get_settings().github_write_token or get_settings().github_token)
    res = client.post_comment(repo, number, body)
    if conn and item_id and item_id > 0:
        save_action(
            conn=conn,
            item_id=item_id,
            tool="post_comment",
            args=args,
            handler_result="proceed",
            dry_run=False,
            idempotency_key=key,
        )
    return {
        "status": "executed",
        "tool": "post_comment",
        "dry_run": False,
        "idempotency_key": key,
        "comment_id": res.get("id"),
        "args": args,
    }


def request_info_comment(
    repo: str,
    number: int,
    template_type: str = "general",
    missing_fields: list[str] | None = None,
    dry_run: bool | None = None,
    conn: sqlite3.Connection | None = None,
    item_id: int | None = None,
    github_client: GitHubClient | None = None,
) -> dict[str, Any]:
    """Post a polite, structured request for missing information."""
    missing_fields = missing_fields or []
    body = _build_info_request_comment(template_type=template_type, missing_fields=missing_fields)
    args = {
        "template_type": template_type,
        "missing_fields": missing_fields,
        "body": body,
    }
    key = compute_idempotency_key("request_info_comment", repo, number, args)

    if conn and has_action_been_executed(conn, key):
        logger.info("Skipping duplicate action: %s", key)
        return {
            "status": "skipped",
            "tool": "request_info_comment",
            "reason": "Duplicate idempotency key match",
            "idempotency_key": key,
            "args": args,
        }

    return post_comment(
        repo=repo,
        number=number,
        body=body,
        dry_run=dry_run,
        conn=conn,
        item_id=item_id,
        github_client=github_client,
    )


def flag_for_maintainer(
    repo: str,
    number: int,
    reason: str,
    suggested_action: str = "review",
    dry_run: bool | None = None,
    conn: sqlite3.Connection | None = None,
    item_id: int | None = None,
) -> dict[str, Any]:
    """Flag an issue or PR for maintainer inspection without modifying GitHub state directly."""
    if dry_run is None:
        dry_run = get_settings().dry_run

    args = {"reason": reason, "suggested_action": suggested_action}
    key = compute_idempotency_key("flag_for_maintainer", repo, number, args)

    if conn and has_action_been_executed(conn, key):
        logger.info("Skipping duplicate action: %s", key)
        return {
            "status": "skipped",
            "tool": "flag_for_maintainer",
            "reason": "Duplicate idempotency key match",
            "idempotency_key": key,
            "args": args,
        }

    logger.info("Flagging %s#%d for maintainer: reason=%s suggested=%s", repo, number, reason, suggested_action)
    if conn and item_id and item_id > 0:
        save_action(
            conn=conn,
            item_id=item_id,
            tool="flag_for_maintainer",
            args=args,
            handler_result="proceed",
            dry_run=dry_run,
            idempotency_key=key,
        )

    return {
        "status": "flagged",
        "tool": "flag_for_maintainer",
        "dry_run": dry_run,
        "idempotency_key": key,
        "args": args,
    }


def close_item(
    repo: str,
    number: int,
    reason: str,
    dry_run: bool | None = None,
    conn: sqlite3.Connection | None = None,
    item_id: int | None = None,
    github_client: GitHubClient | None = None,
) -> dict[str, Any]:
    """Close an issue or pull request.

    SAFETY INVARIANT:
    This tool is guarded by ConfidenceGate and must NEVER execute automatically
    from unconfirmed agent plans. It only executes after explicit maintainer approval.
    """
    if dry_run is None:
        dry_run = get_settings().dry_run

    args = {"reason": reason}
    key = compute_idempotency_key("close_item", repo, number, args)

    if conn and has_action_been_executed(conn, key):
        logger.info("Skipping duplicate action: %s", key)
        return {
            "status": "skipped",
            "tool": "close_item",
            "reason": "Duplicate idempotency key match",
            "idempotency_key": key,
            "args": args,
        }

    if dry_run:
        logger.info("[DRY-RUN] close_item: %s#%d closed with reason: %s", repo, number, reason)
        if conn and item_id and item_id > 0:
            save_action(
                conn=conn,
                item_id=item_id,
                tool="close_item",
                args=args,
                handler_result="confirm",
                dry_run=True,
                idempotency_key=key,
            )
        return {
            "status": "simulated",
            "tool": "close_item",
            "dry_run": True,
            "idempotency_key": key,
            "args": args,
        }

    client = github_client or GitHubClient(token=get_settings().github_write_token or get_settings().github_token)
    res = client.close_item(repo, number, state_reason="not_planned" if "spam" in reason.lower() else "completed")
    if conn and item_id and item_id > 0:
        save_action(
            conn=conn,
            item_id=item_id,
            tool="close_item",
            args=args,
            handler_result="confirm",
            dry_run=False,
            idempotency_key=key,
        )
    return {
        "status": "executed",
        "tool": "close_item",
        "dry_run": False,
        "idempotency_key": key,
        "closed_state": res.get("state"),
        "args": args,
    }


# ---------------------------------------------------------------------------
# Strands Agent Tool Wrappers (@tool)
# ---------------------------------------------------------------------------


@tool(name="apply_label", description="Apply a maintainer label to a GitHub issue or PR.")
def tool_apply_label(repo: str, number: int, label: str) -> str:
    """Strands tool wrapper for apply_label."""
    res = apply_label(repo=repo, number=number, label=label)
    return json.dumps(res)


@tool(name="post_comment", description="Post a helpful triage comment on a GitHub issue or PR.")
def tool_post_comment(repo: str, number: int, body: str) -> str:
    """Strands tool wrapper for post_comment."""
    res = post_comment(repo=repo, number=number, body=body)
    return json.dumps(res)


@tool(name="request_info_comment", description="Politely request missing reproduction steps or information.")
def tool_request_info_comment(repo: str, number: int, template_type: str = "general", missing_fields: list[str] | None = None) -> str:
    """Strands tool wrapper for request_info_comment."""
    res = request_info_comment(repo=repo, number=number, template_type=template_type, missing_fields=missing_fields)
    return json.dumps(res)


@tool(name="flag_for_maintainer", description="Flag an issue or PR for manual maintainer review.")
def tool_flag_for_maintainer(repo: str, number: int, reason: str, suggested_action: str = "review") -> str:
    """Strands tool wrapper for flag_for_maintainer."""
    res = flag_for_maintainer(repo=repo, number=number, reason=reason, suggested_action=suggested_action)
    return json.dumps(res)


@tool(name="close_item", description="Close an issue or pull request (requires human confirmation).")
def tool_close_item(repo: str, number: int, reason: str) -> str:
    """Strands tool wrapper for close_item."""
    res = close_item(repo=repo, number=number, reason=reason)
    return json.dumps(res)


SLOPGATE_TOOLS = [
    tool_apply_label,
    tool_post_comment,
    tool_request_info_comment,
    tool_flag_for_maintainer,
    tool_close_item,
]
