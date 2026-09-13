"""Agents: identity, wake/pause/resume lifecycle, hiring, runs, skills, budgets, keys."""

from __future__ import annotations

from typing import Any

from paperclip_mcp.core import (
    AGENT_ROLES,
    AGENT_STATUSES,
    WAKE_SOURCES,
    WAKE_TRIGGER_DETAILS,
    check_enum,
    clamp,
    company_path,
    fail,
    get,
    mcp,
    patch,
    post,
    resolve_agent_id,
)

# ── Read ───────────────────────────────────────────────────────────────────────


@mcp.tool(tags={"agents"})
async def list_agents() -> Any:
    """List all agents in the company (name, role, status, reportsTo, budget).

    adapterConfig/runtimeConfig are blanked for agent-key callers without agent_config:read.
    """
    return await get(company_path("/agents"))


@mcp.tool(tags={"agents"})
async def get_agent(agent_id: str = "me", company_id: str = "") -> Any:
    """Get one agent (chain of command, budget, status), or the authenticated agent with "me".

    Args:
        agent_id: Agent UUID, agent shortname, or "me" (agent API keys only; board keys get 401,
                  use whoami instead).
        company_id: Only needed to resolve a shortname when the key is a board key.
    """
    if agent_id.strip().lower() == "me":
        return await get("/agents/me")
    return await get(f"/agents/{agent_id}", {"companyId": company_id})


@mcp.tool(tags={"agents"})
async def get_my_inbox() -> Any:
    """Compact list of issues assigned to the authenticated agent (todo/in_progress/blocked)
    with dependency readiness. Agent API keys only."""
    return await get("/agents/me/inbox-lite")


@mcp.tool(tags={"agents"})
async def list_company_skills(q: str = "", sort: str = "") -> Any:
    """List the company skill library (installed skills, independent of which agents enable them).

    Args:
        q: Text filter.
        sort: alphabetical, recent, installs, stars, agents or forks.
    """
    if sort:
        check_enum(sort, ("alphabetical", "recent", "installs", "stars", "agents", "forks"), "sort")
    return await get(company_path("/skills"), {"q": q, "sort": sort})


# ── Wake ───────────────────────────────────────────────────────────────────────


@mcp.tool(tags={"agents"})
async def wake_agent(
    agent_id: str,
    reason: str = "",
    payload: dict[str, Any] | None = None,
    idempotency_key: str = "",
    force_fresh_session: bool = False,
    source: str = "on_demand",
    trigger_detail: str = "manual",
) -> Any:
    """Wake an agent now (start a heartbeat run) with optional context. Returns 202 with the run,
    or {status: "skipped"} when coalesced.

    Board key: any agent (needs agent:wake permission). Agent key: only itself (403 otherwise).
    409 = the agent's reporting chain is invalid.

    Args:
        agent_id: Agent UUID, or "me" for the configured/authenticated agent.
        reason: Why the agent is being woken (shown to the agent).
        payload: Arbitrary JSON context passed to the run.
        idempotency_key: Dedupe key so repeated wakes coalesce.
        force_fresh_session: Start without the stored session.
        source: timer, assignment, on_demand (default) or automation.
        trigger_detail: manual (default), ping, callback or system.
    """
    if agent_id.strip().lower() == "me":
        agent_id = await resolve_agent_id()
    body: dict[str, Any] = {
        "source": check_enum(source, WAKE_SOURCES, "source"),
        "triggerDetail": check_enum(trigger_detail, WAKE_TRIGGER_DETAILS, "trigger_detail"),
    }
    if reason:
        body["reason"] = reason
    if payload is not None:
        body["payload"] = payload
    if idempotency_key:
        body["idempotencyKey"] = idempotency_key
    if force_fresh_session:
        body["forceFreshSession"] = True
    return await post(f"/agents/{agent_id}/wakeup", body)


@mcp.tool(tags={"agents"})
async def invoke_agent_heartbeat(agent_id: str, reason: str = "") -> Any:
    """Legacy heartbeat trigger (POST /agents/{id}/heartbeat/invoke). Prefer wake_agent.

    Args:
        agent_id: Agent UUID, or "me" for the configured/authenticated agent.
        reason: Optional reason shown to the agent.
    """
    if agent_id.strip().lower() == "me":
        agent_id = await resolve_agent_id()
    return await post(f"/agents/{agent_id}/heartbeat/invoke", {"reason": reason} if reason else {})


# ── Lifecycle (board-only) ─────────────────────────────────────────────────────


@mcp.tool(tags={"agents"})
async def pause_agent(agent_id: str) -> Any:
    """Pause an agent: stops heartbeats and cancels its active runs. Board key only.

    Args:
        agent_id: Agent UUID.
    """
    return await post(f"/agents/{agent_id}/pause")


@mcp.tool(tags={"agents"})
async def resume_agent(agent_id: str) -> Any:
    """Resume a paused agent. Board key (or an agent key with agent_config:update grant).
    409 = invalid reporting chain.

    Args:
        agent_id: Agent UUID.
    """
    return await post(f"/agents/{agent_id}/resume")


@mcp.tool(tags={"agents"})
async def clear_agent_error(agent_id: str) -> Any:
    """Move an agent from status "error" back to "idle" so it is scheduled again. Board key only.

    Args:
        agent_id: Agent UUID.
    """
    return await post(f"/agents/{agent_id}/clear-error")


@mcp.tool(tags={"agents"})
async def terminate_agent(agent_id: str) -> Any:
    """Permanently deactivate an agent (irreversible). Board key only.
    A pending_approval agent has its hire approval rejected instead.

    Args:
        agent_id: Agent UUID.
    """
    return await post(f"/agents/{agent_id}/terminate")


@mcp.tool(tags={"agents"})
async def approve_agent(agent_id: str) -> Any:
    """Approve an agent in pending_approval status (resolves its hire approval). Board key only.

    Args:
        agent_id: Agent UUID.
    """
    return await post(f"/agents/{agent_id}/approve")


# ── Hire / configure ───────────────────────────────────────────────────────────


def _agent_body(
    name: str,
    adapter_type: str,
    role: str,
    title: str,
    reports_to: str,
    capabilities: str,
    adapter_config: dict[str, Any] | None,
    runtime_config: dict[str, Any] | None,
    budget_monthly_cents: int | None,
    permissions: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    if not name.strip():
        raise fail("name is required.")
    body: dict[str, Any] = {"name": name, "adapterType": adapter_type or "process"}
    if role:
        body["role"] = check_enum(role, AGENT_ROLES, "role")
    if title:
        body["title"] = title
    if reports_to:
        body["reportsTo"] = reports_to
    if capabilities:
        body["capabilities"] = capabilities
    if adapter_config is not None:
        body["adapterConfig"] = adapter_config
    if runtime_config is not None:
        body["runtimeConfig"] = runtime_config
    if budget_monthly_cents is not None:
        body["budgetMonthlyCents"] = budget_monthly_cents
    if permissions is not None:
        body["permissions"] = permissions
    if metadata is not None:
        body["metadata"] = metadata
    return body


@mcp.tool(tags={"agents"})
async def create_agent(
    name: str,
    adapter_type: str = "claude_local",
    role: str = "general",
    title: str = "",
    reports_to: str = "",
    capabilities: str = "",
    adapter_config: dict[str, Any] | None = None,
    runtime_config: dict[str, Any] | None = None,
    budget_monthly_cents: int | None = None,
    permissions: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Any:
    """Create (hire) an agent directly. Needs the agents:create permission (board key, or an
    agent with canCreateAgents). 409 when the company requires board approval for hires:
    use create_agent_hire instead.

    Args:
        name: Agent display name.
        adapter_type: claude_local, codex_local, gemini_local, opencode_local, cursor_cloud,
                      hermes_local, hermes_gateway, paperclip_runner, http, process, ...
        role: ceo, cto, cmo, cfo, security, engineer, designer, pm, qa, devops, researcher, general.
        title: Job title.
        reports_to: Manager agent UUID.
        capabilities: Free-text capabilities summary.
        adapter_config: Adapter-specific config (model, cwd, env bindings ...).
        runtime_config: Runtime config object.
        budget_monthly_cents: Monthly budget cap in cents.
        permissions: {"canCreateAgents": bool, "canCreateSkills": bool, "trustPreset": ...}.
        metadata: Arbitrary metadata object.
    """
    body = _agent_body(
        name,
        adapter_type,
        role,
        title,
        reports_to,
        capabilities,
        adapter_config,
        runtime_config,
        budget_monthly_cents,
        permissions,
        metadata,
    )
    return await post(company_path("/agents"), body)


@mcp.tool(tags={"agents"})
async def create_agent_hire(
    name: str,
    adapter_type: str = "claude_local",
    role: str = "general",
    title: str = "",
    reports_to: str = "",
    capabilities: str = "",
    adapter_config: dict[str, Any] | None = None,
    runtime_config: dict[str, Any] | None = None,
    budget_monthly_cents: int | None = None,
    permissions: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    source_issue_ids: list[str] | None = None,
) -> Any:
    """Request a hire: creates a pending_approval agent plus a hire_agent approval for the board.
    Same fields as create_agent; source_issue_ids links the originating issues.
    """
    body = _agent_body(
        name,
        adapter_type,
        role,
        title,
        reports_to,
        capabilities,
        adapter_config,
        runtime_config,
        budget_monthly_cents,
        permissions,
        metadata,
    )
    if source_issue_ids:
        body["sourceIssueIds"] = source_issue_ids
    return await post(company_path("/agent-hires"), body)


@mcp.tool(tags={"agents"})
async def update_agent(
    agent_id: str,
    name: str = "",
    title: str = "",
    role: str = "",
    reports_to: str = "",
    capabilities: str = "",
    status: str = "",
    adapter_type: str = "",
    adapter_config: dict[str, Any] | None = None,
    replace_adapter_config: bool = False,
    runtime_config: dict[str, Any] | None = None,
    budget_monthly_cents: int | None = None,
    default_environment_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> Any:
    """Update an agent's profile, manager, status, budget or adapter/runtime config.
    Needs agent_config:update (board key, or the agent itself). adapter_config is shallow-merged
    unless replace_adapter_config=true. Permissions must be changed via the UI/permissions route.

    Args:
        agent_id: Agent UUID.
        name: New name.
        title: New title.
        role: ceo, cto, cmo, cfo, security, engineer, designer, pm, qa, devops, researcher, general.
        reports_to: Manager agent UUID.
        capabilities: Capabilities text.
        status: active, paused, idle, running, error, pending_approval or terminated
                (prefer pause_agent/resume_agent/terminate_agent).
        adapter_type: Change the adapter.
        adapter_config: Adapter config to merge (or replace).
        replace_adapter_config: Replace instead of merge.
        runtime_config: Runtime config object.
        budget_monthly_cents: Monthly budget in cents (prefer set_agent_budget).
        default_environment_id: Environment UUID.
        metadata: Metadata object.
    """
    body: dict[str, Any] = {}
    if name:
        body["name"] = name
    if title:
        body["title"] = title
    if role:
        body["role"] = check_enum(role, AGENT_ROLES, "role")
    if reports_to:
        body["reportsTo"] = reports_to
    if capabilities:
        body["capabilities"] = capabilities
    if status:
        body["status"] = check_enum(status, AGENT_STATUSES, "status")
    if adapter_type:
        body["adapterType"] = adapter_type
    if adapter_config is not None:
        body["adapterConfig"] = adapter_config
        if replace_adapter_config:
            body["replaceAdapterConfig"] = True
    if runtime_config is not None:
        body["runtimeConfig"] = runtime_config
    if budget_monthly_cents is not None:
        body["budgetMonthlyCents"] = budget_monthly_cents
    if default_environment_id:
        body["defaultEnvironmentId"] = default_environment_id
    if metadata is not None:
        body["metadata"] = metadata
    if not body:
        raise fail("No fields to update.")
    return await patch(f"/agents/{agent_id}", body)


@mcp.tool(tags={"agents"})
async def set_agent_budget(agent_id: str, budget_monthly_cents: int) -> Any:
    """Set an agent's monthly budget cap (cents) and its budget policy. Board key only.

    Args:
        agent_id: Agent UUID.
        budget_monthly_cents: Non-negative integer; 0 disables the cap.
    """
    if budget_monthly_cents < 0:
        raise fail("budget_monthly_cents must be >= 0.")
    return await patch(f"/agents/{agent_id}/budgets", {"budgetMonthlyCents": budget_monthly_cents})


@mcp.tool(tags={"agents"})
async def create_agent_api_key(agent_id: str, name: str = "default") -> Any:
    """Mint a long-lived API key for an agent (plaintext shown once). Board key only.

    Args:
        agent_id: Agent UUID.
        name: Key label.
    """
    return await post(f"/agents/{agent_id}/keys", {"name": name or "default"})


# ── Runs ───────────────────────────────────────────────────────────────────────


@mcp.tool(tags={"agents"})
async def list_agent_runs(agent_id: str = "", limit: int = 50, summary: bool = True) -> Any:
    """Heartbeat run history for the company or one agent (status, timings, errors).

    Args:
        agent_id: Agent UUID filter. Leave empty for all agents.
        limit: 1-1000. Default 50.
        summary: Return summary columns only (smaller payload). Default true.
    """
    params: dict[str, Any] = {
        "agentId": agent_id,
        "limit": clamp(limit, 1, 1000),
        "summary": "true" if summary else None,
    }
    return await get(company_path("/heartbeat-runs"), params)


@mcp.tool(tags={"agents"})
async def get_run(run_id: str) -> Any:
    """Get one heartbeat run with execution details, error code and liveness state.

    Args:
        run_id: Heartbeat run UUID.
    """
    return await get(f"/heartbeat-runs/{run_id}")


@mcp.tool(tags={"agents"})
async def cancel_run(run_id: str) -> Any:
    """Cancel a single queued/running heartbeat run without pausing the agent. Board key only.

    Args:
        run_id: Heartbeat run UUID.
    """
    return await post(f"/heartbeat-runs/{run_id}/cancel")


@mcp.tool(tags={"agents"})
async def list_live_runs(limit: int = 50) -> Any:
    """What is running right now: queued/running heartbeat runs with agent name and adapter.

    Args:
        limit: Max runs. Default 50.
    """
    return await get(company_path("/live-runs"), {"limit": clamp(limit, 1, 500)})
