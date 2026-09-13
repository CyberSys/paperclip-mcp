"""Pipelines: staged lanes through which cases move, with automations and review gates."""

from __future__ import annotations

from typing import Any

from paperclip_mcp.core import (
    PIPELINE_REVIEW_DECISIONS,
    check_enum,
    clamp,
    company_path,
    fail,
    get,
    mcp,
    post,
)


@mcp.tool(tags={"pipelines"})
async def list_pipelines() -> Any:
    """List pipelines with stages, open case count, attention count and in-motion count."""
    return await get(company_path("/pipelines"))


@mcp.tool(tags={"pipelines"})
async def get_pipeline(pipeline_id: str) -> Any:
    """Get a pipeline with its stages (keys needed for ingest), transitions and automations.

    Args:
        pipeline_id: Pipeline UUID.
    """
    return await get(f"/pipelines/{pipeline_id}")


@mcp.tool(tags={"pipelines"})
async def list_pipeline_attention(limit: int = 50) -> Any:
    """Pipeline cases waiting on a human: review-stage cases and pending agent suggestions.

    Args:
        limit: 1-100. Default 50.
    """
    return await get(company_path("/pipelines-attention"), {"limit": clamp(limit, 1, 100)})


@mcp.tool(tags={"pipelines"})
async def list_pipeline_cases(
    pipeline_id: str,
    stage_key: str = "",
    q: str = "",
    terminal: bool | None = None,
    include_retired: bool = False,
    parent_case_id: str = "",
) -> Any:
    """List cases in a pipeline, optionally by stage.

    Args:
        pipeline_id: Pipeline UUID.
        stage_key: Stage key filter.
        q: Text search over title/summary.
        terminal: true = only done/cancelled cases, false = only live ones.
        include_retired: Include retired cases.
        parent_case_id: Parent case UUID filter.
    """
    params: dict[str, Any] = {
        "stageKey": stage_key,
        "q": q,
        "terminal": None if terminal is None else ("true" if terminal else "false"),
        "includeRetired": "true" if include_retired else None,
        "parentCaseId": parent_case_id,
    }
    return await get(f"/pipelines/{pipeline_id}/cases", params)


@mcp.tool(tags={"pipelines"})
async def ingest_pipeline_case(
    pipeline_id: str,
    title: str,
    case_key: str = "",
    summary: str = "",
    fields: dict[str, Any] | None = None,
    stage_key: str = "",
    parent_case_id: str = "",
) -> Any:
    """Drop a case into a pipeline (first stage by default), kicking off stage automations.
    Board key (agent keys need a run id). Returns 201, or 200 when case_key already exists (upsert).

    Args:
        pipeline_id: Pipeline UUID.
        title: Case title (1-500).
        case_key: Stable external key for upserts (max 1024).
        summary: Case summary (max 8000).
        fields: Arbitrary structured fields.
        stage_key: Initial stage key (default: first stage).
        parent_case_id: Parent case UUID.
    """
    if not title.strip():
        raise fail("title is required.")
    body: dict[str, Any] = {"title": title}
    if case_key:
        body["caseKey"] = case_key
    if summary:
        body["summary"] = summary
    if fields is not None:
        body["fields"] = fields
    if stage_key:
        body["stageKey"] = stage_key
    if parent_case_id:
        body["parentCaseId"] = parent_case_id
    return await post(f"/pipelines/{pipeline_id}/cases", body)


@mcp.tool(tags={"pipelines"})
async def review_pipeline_case(
    case_id: str,
    decision: str,
    expected_version: int,
    reason: str = "",
) -> Any:
    """Decide a case sitting in a review stage: approve, reject or request_changes. Board key.

    Args:
        case_id: Case UUID.
        decision: approve, reject or request_changes.
        expected_version: Current case version (from list_pipeline_cases); stale -> 409.
        reason: Optional reason (max 4000).
    """
    body: dict[str, Any] = {
        "decision": check_enum(decision, PIPELINE_REVIEW_DECISIONS, "decision"),
        "expectedVersion": expected_version,
    }
    if reason:
        body["reason"] = reason
    return await post(f"/cases/{case_id}/review", body)
