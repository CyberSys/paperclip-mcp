"""Routines: recurring work fired by schedule, webhook or API."""

from __future__ import annotations

from typing import Any

from paperclip_mcp.core import (
    ISSUE_PRIORITIES,
    ROUTINE_CATCH_UP_POLICIES,
    ROUTINE_CONCURRENCY_POLICIES,
    ROUTINE_STATUSES,
    ROUTINE_TRIGGER_KINDS,
    ROUTINE_TRIGGER_SIGNING_MODES,
    check_enum,
    clamp,
    company_path,
    fail,
    get,
    mcp,
    patch,
    post,
)


@mcp.tool(tags={"routines"})
async def list_routines(project_id: str = "") -> Any:
    """List routines with their triggers (cron, nextRunAt, lastFiredAt), last run and active issue.

    Args:
        project_id: Project UUID filter.
    """
    return await get(company_path("/routines"), {"projectId": project_id})


@mcp.tool(tags={"routines"})
async def get_routine(routine_id: str) -> Any:
    """Get one routine with project, assignee, triggers and recent runs.

    Args:
        routine_id: Routine UUID.
    """
    return await get(f"/routines/{routine_id}")


def _routine_fields(
    title: str,
    description: str,
    assignee_agent_id: str,
    project_id: str,
    goal_id: str,
    parent_issue_id: str,
    priority: str,
    status: str,
    concurrency_policy: str,
    catch_up_policy: str,
) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if title:
        body["title"] = title
    if description:
        body["description"] = description
    if assignee_agent_id:
        body["assigneeAgentId"] = assignee_agent_id
    if project_id:
        body["projectId"] = project_id
    if goal_id:
        body["goalId"] = goal_id
    if parent_issue_id:
        body["parentIssueId"] = parent_issue_id
    if priority:
        body["priority"] = check_enum(priority, ISSUE_PRIORITIES, "priority")
    if status:
        body["status"] = check_enum(status, ROUTINE_STATUSES, "status")
    if concurrency_policy:
        body["concurrencyPolicy"] = check_enum(
            concurrency_policy, ROUTINE_CONCURRENCY_POLICIES, "concurrency_policy"
        )
    if catch_up_policy:
        body["catchUpPolicy"] = check_enum(
            catch_up_policy, ROUTINE_CATCH_UP_POLICIES, "catch_up_policy"
        )
    return body


@mcp.tool(tags={"routines"})
async def create_routine(
    title: str,
    description: str = "",
    assignee_agent_id: str = "",
    project_id: str = "",
    goal_id: str = "",
    parent_issue_id: str = "",
    priority: str = "medium",
    status: str = "active",
    concurrency_policy: str = "coalesce_if_active",
    catch_up_policy: str = "skip_missed",
) -> Any:
    """Create a routine. It fires only via run_routine until a trigger is added
    (create_routine_trigger).
    Agent keys may only create routines assigned to themselves.

    Args:
        title: Routine name (1-200 chars).
        description: What each run should do (Markdown).
        assignee_agent_id: Agent UUID that receives each run.
        project_id: Project UUID for created run issues.
        goal_id: Goal UUID to link runs to.
        parent_issue_id: Parent issue UUID for created run issues.
        priority: critical, high, medium (default) or low.
        status: active (default), paused or archived.
        concurrency_policy: coalesce_if_active (default), always_enqueue or skip_if_active.
        catch_up_policy: skip_missed (default) or enqueue_missed_with_cap.
    """
    if not title.strip():
        raise fail("title is required.")
    body = _routine_fields(
        title,
        description,
        assignee_agent_id,
        project_id,
        goal_id,
        parent_issue_id,
        priority,
        status,
        concurrency_policy,
        catch_up_policy,
    )
    return await post(company_path("/routines"), body)


@mcp.tool(tags={"routines"})
async def update_routine(
    routine_id: str,
    title: str = "",
    description: str = "",
    assignee_agent_id: str = "",
    project_id: str = "",
    goal_id: str = "",
    parent_issue_id: str = "",
    priority: str = "",
    status: str = "",
    concurrency_policy: str = "",
    catch_up_policy: str = "",
    base_revision_id: str = "",
) -> Any:
    """Update a routine; use status to pause/resume/archive it (archived is terminal).
    Agent keys may only update their own routines and cannot reassign them.

    Args:
        routine_id: Routine UUID.
        title: New title.
        description: New description.
        assignee_agent_id: New assignee agent UUID.
        project_id: Project UUID.
        goal_id: Goal UUID.
        parent_issue_id: Parent issue UUID.
        priority: critical, high, medium or low.
        status: active, paused or archived.
        concurrency_policy: coalesce_if_active, always_enqueue or skip_if_active.
        catch_up_policy: skip_missed or enqueue_missed_with_cap.
        base_revision_id: Latest revision id for optimistic concurrency (stale -> 409).
    """
    body = _routine_fields(
        title,
        description,
        assignee_agent_id,
        project_id,
        goal_id,
        parent_issue_id,
        priority,
        status,
        concurrency_policy,
        catch_up_policy,
    )
    if base_revision_id:
        body["baseRevisionId"] = base_revision_id
    if not body:
        raise fail("No fields to update.")
    return await patch(f"/routines/{routine_id}", body)


@mcp.tool(tags={"routines"})
async def run_routine(
    routine_id: str,
    trigger_id: str = "",
    payload: dict[str, Any] | None = None,
    variables: dict[str, Any] | None = None,
    idempotency_key: str = "",
) -> Any:
    """Fire a routine now, bypassing its schedule (concurrency policy still applies).
    Returns 202 with the run status: received, coalesced, skipped or issue_created.

    Args:
        routine_id: Routine UUID.
        trigger_id: Attribute the run to this trigger (403 if not on the routine, 409 if disabled).
        payload: JSON context for the run.
        variables: Values for the routine's declared variables.
        idempotency_key: Dedupe key.
    """
    body: dict[str, Any] = {"source": "manual"}
    if trigger_id:
        body["triggerId"] = trigger_id
    if payload is not None:
        body["payload"] = payload
    if variables is not None:
        body["variables"] = variables
    if idempotency_key:
        body["idempotencyKey"] = idempotency_key
    return await post(f"/routines/{routine_id}/run", body)


@mcp.tool(tags={"routines"})
async def list_routine_runs(routine_id: str, limit: int = 50) -> Any:
    """Recent runs of a routine: status (received|coalesced|skipped|issue_created|completed|failed),
    source, linked issue and failure reason.

    Args:
        routine_id: Routine UUID.
        limit: Max runs. Default 50.
    """
    return await get(f"/routines/{routine_id}/runs", {"limit": clamp(limit, 1, 500)})


@mcp.tool(tags={"routines"})
async def create_routine_trigger(
    routine_id: str,
    kind: str,
    cron_expression: str = "",
    timezone: str = "UTC",
    label: str = "",
    enabled: bool = True,
    signing_mode: str = "",
    replay_window_sec: int | None = None,
) -> Any:
    """Add a trigger to a routine: schedule (cron), webhook (inbound HTTP POST) or api (manual).
    Webhook triggers return one-time secret material.

    Args:
        routine_id: Routine UUID.
        kind: schedule, webhook or api.
        cron_expression: Required for schedule, e.g. "0 9 * * 1".
        timezone: IANA timezone for schedule triggers. Default UTC.
        label: Trigger label (max 120).
        enabled: Default true.
        signing_mode: Webhook only: bearer (default), hmac_sha256, github_hmac or none.
        replay_window_sec: Webhook only: 30-86400 (default 300).
    """
    body: dict[str, Any] = {
        "kind": check_enum(kind, ROUTINE_TRIGGER_KINDS, "kind"),
        "enabled": enabled,
    }
    if label:
        body["label"] = label
    if kind == "schedule":
        if not cron_expression.strip():
            raise fail("cron_expression is required for schedule triggers.")
        body["cronExpression"] = cron_expression
        body["timezone"] = timezone or "UTC"
    elif kind == "webhook":
        if signing_mode:
            body["signingMode"] = check_enum(
                signing_mode, ROUTINE_TRIGGER_SIGNING_MODES, "signing_mode"
            )
        if replay_window_sec is not None:
            body["replayWindowSec"] = clamp(replay_window_sec, 30, 86400)
    return await post(f"/routines/{routine_id}/triggers", body)
