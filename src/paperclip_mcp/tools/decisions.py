"""Decisions: agent-proposed choices (1-8 options with issue effects) awaiting a human."""

from __future__ import annotations

from typing import Any

from paperclip_mcp.core import DECISION_STATUSES, check_enum, clamp, company_path, get, mcp, post


@mcp.tool(tags={"decisions"})
async def list_decisions(
    status: str = "open",
    target_issue_id: str = "",
    origin_agent_id: str = "",
    limit: int = 50,
) -> Any:
    """List decisions proposed by agents. Open decisions are the human queue agents block on.
    Board key only.

    Args:
        status: open (default), decided, expired or cancelled. "" for all.
        target_issue_id: Issue UUID filter.
        origin_agent_id: Proposing agent UUID filter.
        limit: 1-100. Default 50.
    """
    if status:
        check_enum(status, DECISION_STATUSES, "status")
    params: dict[str, Any] = {
        "status": status,
        "targetIssueId": target_issue_id,
        "originAgentId": origin_agent_id,
        "limit": clamp(limit, 1, 100),
    }
    return await get(company_path("/decisions"), params)


@mcp.tool(tags={"decisions"})
async def get_decision(decision_id: str) -> Any:
    """Get one decision with its options, inputs and effects. Board key, or the origin agent.

    Args:
        decision_id: Decision UUID.
    """
    return await get(f"/decisions/{decision_id}")


@mcp.tool(tags={"decisions"})
async def decide_decision(
    decision_id: str,
    option_id: str,
    input_values: dict[str, str] | None = None,
    idempotency_key: str = "",
) -> Any:
    """Resolve a decision by choosing an option; the server applies its effects. Board key only.

    Args:
        decision_id: Decision UUID.
        option_id: Chosen option id (see get_decision).
        input_values: Values for the decision's declared inputs, keyed by input id.
        idempotency_key: Dedupe key.
    """
    body: dict[str, Any] = {"optionId": option_id}
    if input_values:
        body["inputValues"] = input_values
    if idempotency_key:
        body["idempotencyKey"] = idempotency_key
    return await post(f"/decisions/{decision_id}/decide", body)


@mcp.tool(tags={"decisions"})
async def dismiss_decision(decision_id: str, reason: str = "") -> Any:
    """Dismiss a decision without choosing an option (counts as rejected). Board key only.

    Args:
        decision_id: Decision UUID.
        reason: Optional reason.
    """
    return await post(f"/decisions/{decision_id}/dismiss", {"reason": reason} if reason else {})
