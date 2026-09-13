"""Dashboard, costs, budgets, activity log and the operator attention feed."""

from __future__ import annotations

from typing import Any

from paperclip_mcp.core import (
    ATTENTION_SORTS,
    COST_GROUP_BYS,
    check_enum,
    clamp,
    company_path,
    fail,
    get,
    mcp,
    patch,
)


@mcp.tool(tags={"monitoring"})
async def get_dashboard() -> Any:
    """Company health in one call: agents by status, tasks by status, month spend vs budget,
    pending approvals, budget incidents and a 14-day run histogram."""
    return await get(company_path("/dashboard"))


@mcp.tool(tags={"monitoring"})
async def get_cost_summary(from_date: str = "", to_date: str = "") -> Any:
    """Total spend vs monthly budget: {spendCents, budgetCents, utilizationPercent}.

    Without a date range spendCents is ALL-TIME. Pass from_date = first day of the month for
    month-to-date, or read get_dashboard.costs.monthSpendCents.

    Args:
        from_date: ISO date/datetime lower bound.
        to_date: ISO date/datetime upper bound.
    """
    return await get(company_path("/costs/summary"), {"from": from_date, "to": to_date})


@mcp.tool(tags={"monitoring"})
async def get_cost_breakdown(
    group_by: str = "agent", from_date: str = "", to_date: str = ""
) -> Any:
    """Spend breakdown by agent, project, provider, agent_model or biller (tokens, cost, runs).
    Use it to spot runaway agents.

    Args:
        group_by: agent (default), project, provider, agent_model or biller.
        from_date: ISO date lower bound (omit for all-time).
        to_date: ISO date upper bound.
    """
    segment = check_enum(group_by, COST_GROUP_BYS, "group_by").replace("_", "-")
    return await get(company_path(f"/costs/by-{segment}"), {"from": from_date, "to": to_date})


@mcp.tool(tags={"monitoring"})
async def get_cost_window_spend() -> Any:
    """Rolling 5h / 24h / 7d spend per provider: the fastest signal for a runaway agent."""
    return await get(company_path("/costs/window-spend"))


@mcp.tool(tags={"monitoring"})
async def get_budget_overview() -> Any:
    """Budget policies (company/agent/project scope) with remaining amount, warning/hard-stop
    status, open incidents and paused agents/projects."""
    return await get(company_path("/budgets/overview"))


@mcp.tool(tags={"monitoring"})
async def set_company_budget(budget_monthly_cents: int) -> Any:
    """Set the company's monthly budget cap in cents (alert at 80%, hard stop at 100%).
    Board key only.

    Args:
        budget_monthly_cents: Non-negative integer.
    """
    if budget_monthly_cents < 0:
        raise fail("budget_monthly_cents must be >= 0.")
    return await patch(company_path("/budgets"), {"budgetMonthlyCents": budget_monthly_cents})


@mcp.tool(tags={"monitoring"})
async def list_activity(
    agent_id: str = "",
    entity_type: str = "",
    entity_id: str = "",
    limit: int = 50,
) -> Any:
    """Company-wide audit trail (all mutations), newest first. Unpaginated.

    Args:
        agent_id: Filter by acting agent UUID.
        entity_type: issue, agent, approval, project, goal, ...
        entity_id: Entity UUID (for issues the UUID, not "PAP-42"; use get_issue_activity for that).
        limit: 1-500. Default 50.
    """
    params: dict[str, Any] = {
        "agentId": agent_id,
        "entityType": entity_type,
        "entityId": entity_id,
        "limit": clamp(limit, 1, 500),
    }
    return await get(company_path("/activity"), params)


@mcp.tool(tags={"monitoring"})
async def get_attention_feed(
    limit: int = 50,
    sort: str = "activity",
    include_dismissed: bool = False,
    queue: str = "",
    cursor: str = "",
) -> Any:
    """What needs a human now: approvals, decisions, thread interactions, failed runs, budget
    alerts and blockers, ranked by severity. Board key only (agent keys: use get_sidebar_badges
    and list_approvals).

    Args:
        limit: 1-100. Default 50.
        sort: activity (default) or decide.
        include_dismissed: Include dismissed/snoozed items.
        queue: Decision-queue key to filter by.
        cursor: nextCursor from a previous page.
    """
    params: dict[str, Any] = {
        "limit": clamp(limit, 1, 100),
        "sort": check_enum(sort, ATTENTION_SORTS, "sort"),
        "includeDismissed": "true" if include_dismissed else None,
        "queue": queue,
        "cursor": cursor,
    }
    return await get(company_path("/attention"), params)


@mcp.tool(tags={"monitoring"})
async def get_sidebar_badges() -> Any:
    """Cheap attention counters for any key: {inbox, approvals, failedRuns, joinRequests}."""
    return await get(company_path("/sidebar-badges"))
