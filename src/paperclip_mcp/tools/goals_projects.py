"""Goals (the "why") and projects (the "what")."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from paperclip_mcp.core import (
    GOAL_LEVELS,
    GOAL_STATUSES,
    PROJECT_STATUSES,
    check_enum,
    company_path,
    delete,
    fail,
    get,
    mcp,
    patch,
    post,
)

# ── Goals ──────────────────────────────────────────────────────────────────────


@mcp.tool(tags={"goals"})
async def list_goals() -> Any:
    """List the company's goals: title, level (company|team|agent|task), status, parent, owner.
    Projects are separate: use list_projects."""
    return await get(company_path("/goals"))


@mcp.tool(tags={"goals"})
async def get_goal(goal_id: str) -> Any:
    """Get one goal by UUID.

    Args:
        goal_id: Goal UUID.
    """
    return await get(f"/goals/{goal_id}")


@mcp.tool(tags={"goals"})
async def create_goal(
    title: str,
    description: str = "",
    level: str = "company",
    status: str = "active",
    parent_id: str = "",
    owner_agent_id: str = "",
) -> Any:
    """Create a goal. Agents are guided by level="company", status="active" root goals, so those are
    the defaults here.

    Args:
        title: Goal title.
        description: Context, success criteria, constraints (Markdown).
        level: company, team, agent or task. Default: company.
        status: planned, active, achieved or cancelled. Default: active.
        parent_id: Parent goal UUID for a sub-goal.
        owner_agent_id: Owning agent UUID.
    """
    if not title.strip():
        raise fail("title is required.")
    body: dict[str, Any] = {
        "title": title,
        "level": check_enum(level, GOAL_LEVELS, "level"),
        "status": check_enum(status, GOAL_STATUSES, "status"),
    }
    if description:
        body["description"] = description
    if parent_id:
        body["parentId"] = parent_id
    if owner_agent_id:
        body["ownerAgentId"] = owner_agent_id
    return await post(company_path("/goals"), body)


@mcp.tool(tags={"goals"})
async def update_goal(
    goal_id: str,
    title: str = "",
    description: str = "",
    level: str = "",
    status: str = "",
    parent_id: str = "",
    owner_agent_id: str = "",
) -> Any:
    """Update a goal's title, description, level, status, parent or owner. Only given fields change.

    Args:
        goal_id: Goal UUID.
        title: New title.
        description: New description.
        level: company, team, agent or task.
        status: planned, active, achieved or cancelled.
        parent_id: New parent goal UUID.
        owner_agent_id: New owner agent UUID.
    """
    body: dict[str, Any] = {}
    if title:
        body["title"] = title
    if description:
        body["description"] = description
    if level:
        body["level"] = check_enum(level, GOAL_LEVELS, "level")
    if status:
        body["status"] = check_enum(status, GOAL_STATUSES, "status")
    if parent_id:
        body["parentId"] = parent_id
    if owner_agent_id:
        body["ownerAgentId"] = owner_agent_id
    if not body:
        raise fail(
            "No fields to update. Provide at least one of: title, description, level, status, "
            "parent_id, owner_agent_id."
        )
    return await patch(f"/goals/{goal_id}", body)


@mcp.tool(tags={"goals"})
async def delete_goal(goal_id: str) -> Any:
    """Hard-delete a goal. Fails if sub-goals or projects still reference it; prefer
    update_goal(status="cancelled").

    Args:
        goal_id: Goal UUID.
    """
    return await delete(f"/goals/{goal_id}")


# ── Projects ───────────────────────────────────────────────────────────────────


@mcp.tool(tags={"projects"})
async def list_projects(include_archived: bool = False) -> Any:
    """List projects with goals, workspaces, task counts and budget.

    Args:
        include_archived: Also return archived projects.
    """
    return await get(
        company_path("/projects"), {"includeArchived": "true" if include_archived else None}
    )


@mcp.tool(tags={"projects"})
async def get_project(project_id: str) -> Any:
    """Get one project (workspaces, goals, codebase) by UUID or shortname (url key).

    Args:
        project_id: Project UUID or shortname. 409 if the shortname is ambiguous.
    """
    return await get(f"/projects/{project_id}")


@mcp.tool(tags={"projects"})
async def create_project(
    name: str,
    description: str = "",
    status: str = "backlog",
    goal_ids: list[str] | None = None,
    lead_agent_id: str = "",
    target_date: str = "",
    color: str = "",
    icon: str = "",
    workspace_cwd: str = "",
    workspace_repo_url: str = "",
    workspace_repo_ref: str = "",
    workspace_name: str = "",
    idempotency_key: str = "",
) -> Any:
    """Create a project, optionally seeded with a primary workspace (local path and/or git repo).

    Args:
        name: Project name (auto-suffixed on shortname collision).
        description: Markdown description.
        status: backlog (default), planned, in_progress, completed or cancelled.
        goal_ids: Goal UUIDs to link.
        lead_agent_id: Lead agent UUID.
        target_date: Target date (YYYY-MM-DD).
        color: Display color.
        icon: Icon name (folder, rocket, code, terminal, database, globe, ...).
        workspace_cwd: Local working directory for the primary workspace.
        workspace_repo_url: Git repository URL for the primary workspace.
        workspace_repo_ref: Git ref/branch (e.g. main).
        workspace_name: Workspace label.
        idempotency_key: Safe-retry key.
    """
    if not name.strip():
        raise fail("name is required.")
    body: dict[str, Any] = {"name": name, "status": check_enum(status, PROJECT_STATUSES, "status")}
    if description:
        body["description"] = description
    if goal_ids:
        body["goalIds"] = goal_ids
    if lead_agent_id:
        body["leadAgentId"] = lead_agent_id
    if target_date:
        body["targetDate"] = target_date
    if color:
        body["color"] = color
    if icon:
        body["icon"] = icon
    if workspace_cwd or workspace_repo_url:
        workspace: dict[str, Any] = {"isPrimary": True}
        if workspace_name:
            workspace["name"] = workspace_name
        if workspace_cwd:
            workspace["cwd"] = workspace_cwd
        if workspace_repo_url:
            workspace["repoUrl"] = workspace_repo_url
        if workspace_repo_ref:
            workspace["repoRef"] = workspace_repo_ref
        body["workspace"] = workspace
    if idempotency_key:
        body["idempotencyKey"] = idempotency_key
    return await post(company_path("/projects"), body)


@mcp.tool(tags={"projects"})
async def update_project(
    project_id: str,
    name: str = "",
    description: str = "",
    status: str = "",
    goal_ids: list[str] | None = None,
    lead_agent_id: str = "",
    target_date: str = "",
    color: str = "",
    icon: str = "",
    archived: bool | None = None,
) -> Any:
    """Update a project (status, goals, lead, archive flag). Only provided fields change.

    Args:
        project_id: Project UUID or shortname.
        name: New name.
        description: New description.
        status: backlog, planned, in_progress, completed or cancelled.
        goal_ids: Replace linked goals ([] clears).
        lead_agent_id: Lead agent UUID.
        target_date: YYYY-MM-DD.
        color: Display color.
        icon: Icon name.
        archived: true archives now, false un-archives. Omit to leave unchanged.
    """
    body: dict[str, Any] = {}
    if name:
        body["name"] = name
    if description:
        body["description"] = description
    if status:
        body["status"] = check_enum(status, PROJECT_STATUSES, "status")
    if goal_ids is not None:
        body["goalIds"] = goal_ids
    if lead_agent_id:
        body["leadAgentId"] = lead_agent_id
    if target_date:
        body["targetDate"] = target_date
    if color:
        body["color"] = color
    if icon:
        body["icon"] = icon
    if archived is True:
        body["archivedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    elif archived is False:
        body["archivedAt"] = None
    if not body:
        raise fail("No fields to update.")
    return await patch(f"/projects/{project_id}", body)
