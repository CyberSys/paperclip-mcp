"""Approvals: board review of hires, strategy and other gated actions."""

from __future__ import annotations

from typing import Any

from paperclip_mcp.core import (
    APPROVAL_STATUSES,
    APPROVAL_TYPES,
    check_enum,
    company_path,
    fail,
    get,
    mcp,
    post,
)


@mcp.tool(tags={"approvals"})
async def list_approvals(status: str = "pending") -> Any:
    """List approval requests in the company.

    Args:
        status: pending (default), revision_requested, approved, rejected or cancelled.
                Pass "" for all statuses.
    """
    if status:
        check_enum(status, APPROVAL_STATUSES, "status")
    return await get(company_path("/approvals"), {"status": status})


@mcp.tool(tags={"approvals"})
async def get_approval(approval_id: str) -> Any:
    """Get one approval: type, status, payload, decision note and who decided.

    Args:
        approval_id: Approval UUID.
    """
    return await get(f"/approvals/{approval_id}")


@mcp.tool(tags={"approvals"})
async def create_approval(
    type: str,
    payload: dict[str, Any] | None = None,
    requested_by_agent_id: str = "",
    issue_ids: list[str] | None = None,
) -> Any:
    """Open a board approval request, optionally linked to issues.

    Args:
        type: hire_agent, approve_ceo_strategy, budget_override_required or request_board_approval.
        payload: Free-form JSON describing what needs approval.
        requested_by_agent_id: Requesting agent UUID (defaults to the calling agent).
        issue_ids: Issue UUIDs to link.
    """
    body: dict[str, Any] = {
        "type": check_enum(type, APPROVAL_TYPES, "type"),
        "payload": payload or {},
    }
    if requested_by_agent_id:
        body["requestedByAgentId"] = requested_by_agent_id
    if issue_ids:
        body["issueIds"] = issue_ids
    return await post(company_path("/approvals"), body)


def _decision_body(decision_note: str) -> dict[str, Any]:
    return {"decisionNote": decision_note} if decision_note else {}


@mcp.tool(tags={"approvals"})
async def approve(approval_id: str, decision_note: str = "") -> Any:
    """Approve a pending or revision_requested approval. Board key only (agent keys get 403).

    Approving a hire_agent approval activates the agent; the requesting agent is woken.

    Args:
        approval_id: Approval UUID.
        decision_note: Optional note stored with the decision.
    """
    return await post(f"/approvals/{approval_id}/approve", _decision_body(decision_note))


@mcp.tool(tags={"approvals"})
async def reject(approval_id: str, decision_note: str = "") -> Any:
    """Reject a pending or revision_requested approval. Board key only.

    Rejecting a hire_agent approval TERMINATES the pending agent.

    Args:
        approval_id: Approval UUID.
        decision_note: Reason (strongly recommended).
    """
    return await post(f"/approvals/{approval_id}/reject", _decision_body(decision_note))


@mcp.tool(tags={"approvals"})
async def request_approval_revision(approval_id: str, decision_note: str) -> Any:
    """Ask the requester to revise a pending approval instead of rejecting it. Board key only.

    Args:
        approval_id: Approval UUID.
        decision_note: What must change before approval (required).
    """
    if not decision_note.strip():
        raise fail("decision_note is required when requesting a revision.")
    return await post(f"/approvals/{approval_id}/request-revision", {"decisionNote": decision_note})


@mcp.tool(tags={"approvals"})
async def resubmit_approval(approval_id: str, payload: dict[str, Any] | None = None) -> Any:
    """Resubmit a revision_requested approval (back to pending). Agent keys: requesting agent only.

    Args:
        approval_id: Approval UUID.
        payload: Replacement payload; omit to keep the existing one.
    """
    return await post(f"/approvals/{approval_id}/resubmit", {"payload": payload} if payload else {})


@mcp.tool(tags={"approvals"})
async def list_approval_issues(approval_id: str) -> Any:
    """List the issues linked to an approval.

    Args:
        approval_id: Approval UUID.
    """
    return await get(f"/approvals/{approval_id}/issues")


@mcp.tool(tags={"approvals"})
async def list_approval_comments(approval_id: str) -> Any:
    """List the discussion thread on an approval.

    Args:
        approval_id: Approval UUID.
    """
    return await get(f"/approvals/{approval_id}/comments")


@mcp.tool(tags={"approvals"})
async def add_approval_comment(approval_id: str, body: str) -> Any:
    """Comment on an approval (works with agent and board keys).

    Args:
        approval_id: Approval UUID.
        body: Comment text.
    """
    if not body.strip():
        raise fail("body must not be empty.")
    return await post(f"/approvals/{approval_id}/comments", {"body": body})
