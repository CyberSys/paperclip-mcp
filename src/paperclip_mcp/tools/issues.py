"""Issues: CRUD, checkout/release, comments, labels, documents, interactions, diagnostics."""

from __future__ import annotations

from typing import Any

from paperclip_mcp.core import (
    CHECKOUT_DEFAULT_STATUSES,
    INTERACTION_CONTINUATION_POLICIES,
    INTERACTION_KINDS,
    INTERACTION_RESOLVER_POLICIES,
    ISSUE_OPEN_STATUSES,
    ISSUE_PRIORITIES,
    ISSUE_REVIEW_POLICIES,
    ISSUE_STATUSES,
    check_enum,
    check_enum_list,
    clamp,
    company_path,
    delete,
    fail,
    get,
    mcp,
    patch,
    post,
    put,
    resolve_agent_id,
)

# ── CRUD ───────────────────────────────────────────────────────────────────────


@mcp.tool(tags={"issues"})
async def list_issues(
    status: str = ",".join(ISSUE_OPEN_STATUSES),
    assignee_agent_id: str = "",
    project_id: str = "",
    label_id: str = "",
    parent_id: str = "",
    q: str = "",
    limit: int = 100,
    offset: int = 0,
    compact: bool = False,
    sort_field: str = "",
    sort_dir: str = "",
    updated_since: str = "",
) -> Any:
    """List issues (tasks) in the active company, sorted by priority.

    Args:
        status: Comma-separated statuses. Allowed: backlog, todo, in_progress, in_review,
                done, blocked, cancelled. Default: every open status (all but done/cancelled).
                Pass "" to include every status.
        assignee_agent_id: Agent UUID to filter by, or the literal "null" for unassigned issues.
        project_id: Project UUID filter.
        label_id: Label UUID filter (resolve names with list_labels).
        parent_id: Parent issue UUID: list only its direct sub-issues.
        q: Free-text search over title/description.
        limit: 1-1000 (server default 500). Default 100.
        offset: Pagination offset.
        compact: Return the compact view (fewer fields) to save tokens.
        sort_field: "updated" or "id". Leave empty for priority order.
        sort_dir: "asc" or "desc".
        updated_since: ISO-8601 timestamp; only issues updated after it.
    """
    if status:
        check_enum_list(status.split(","), ISSUE_STATUSES, "status")
    if sort_field:
        check_enum(sort_field, ("updated", "id"), "sort_field")
    if sort_dir:
        check_enum(sort_dir, ("asc", "desc"), "sort_dir")
    params: dict[str, Any] = {
        "status": status,
        "assigneeAgentId": assignee_agent_id,
        "projectId": project_id,
        "labelId": label_id,
        "parentId": parent_id,
        "q": q,
        "limit": clamp(limit, 1, 1000),
        "offset": offset or None,
        "view": "compact" if compact else None,
        "sortField": sort_field,
        "sortDir": sort_dir,
        "updatedSince": updated_since,
    }
    return await get(company_path("/issues"), params)


@mcp.tool(tags={"issues"})
async def get_issue(issue_id: str) -> Any:
    """Get one issue with project, goal, ancestors, blockedBy/blocks, work products and plan.

    Args:
        issue_id: Issue UUID or human identifier (e.g. "PAP-42").
    """
    return await get(f"/issues/{issue_id}")


@mcp.tool(tags={"issues"})
async def get_heartbeat_context(issue_id: str, wake_comment_id: str = "") -> Any:
    """Compact working context for an issue: issue, ancestors, project, goal, comment cursor,
    attachments, continuation summary and current execution workspace. Cheaper than get_issue.

    Args:
        issue_id: Issue UUID or identifier.
        wake_comment_id: Comment UUID that triggered the wake; adds it and review context.
    """
    return await get(f"/issues/{issue_id}/heartbeat-context", {"wakeCommentId": wake_comment_id})


@mcp.tool(tags={"issues"})
async def create_issue(
    title: str,
    description: str = "",
    status: str = "",
    priority: str = "medium",
    assignee_agent_id: str = "",
    project_id: str = "",
    goal_id: str = "",
    parent_issue_id: str = "",
    label_ids: list[str] | None = None,
    blocked_by_issue_ids: list[str] | None = None,
    billing_code: str = "",
    review_policy: str = "",
    idempotency_key: str = "",
    allow_duplicate: bool = False,
) -> Any:
    """Create an issue (task), optionally assigned to an agent or nested under a parent.

    Recent-title duplicate detection: creating an issue whose title matches a recent open issue
    under the same parent returns the EXISTING issue (flagged `deduplicated: true`) unless
    allow_duplicate is set.

    Args:
        title: Short imperative title.
        description: Markdown body with instructions/context.
        status: backlog, todo, in_progress, in_review, done, blocked or cancelled.
                Server default: "todo" when an assignee is given, else "backlog".
        priority: critical, high, medium or low. Default: medium.
        assignee_agent_id: Agent UUID (must be a UUID on create).
        project_id: Project UUID.
        goal_id: Goal UUID.
        parent_issue_id: Parent issue UUID to create a sub-issue.
        label_ids: Label UUIDs (see list_labels).
        blocked_by_issue_ids: Issue UUIDs that must finish first.
        billing_code: Free-form billing code.
        review_policy: anyone, not_creator or human_only.
        idempotency_key: Safe-retry key; a replay returns the existing issue.
        allow_duplicate: Bypass recent-title duplicate detection.
    """
    if not title.strip():
        raise fail("title is required.")
    check_enum(priority, ISSUE_PRIORITIES, "priority")
    body: dict[str, Any] = {"title": title, "priority": priority}
    if allow_duplicate:
        body["allowDuplicate"] = True
    if status:
        body["status"] = check_enum(status, ISSUE_STATUSES, "status")
    if description:
        body["description"] = description
    if assignee_agent_id:
        body["assigneeAgentId"] = assignee_agent_id
    if project_id:
        body["projectId"] = project_id
    if goal_id:
        body["goalId"] = goal_id
    if parent_issue_id:
        body["parentId"] = parent_issue_id
    if label_ids:
        body["labelIds"] = label_ids
    if blocked_by_issue_ids:
        body["blockedByIssueIds"] = blocked_by_issue_ids
    if billing_code:
        body["billingCode"] = billing_code
    if review_policy:
        body["reviewPolicy"] = check_enum(review_policy, ISSUE_REVIEW_POLICIES, "review_policy")
    if idempotency_key:
        body["idempotencyKey"] = idempotency_key
    return await post(company_path("/issues"), body)


@mcp.tool(tags={"issues"})
async def update_issue(
    issue_id: str,
    title: str = "",
    description: str = "",
    status: str = "",
    priority: str = "",
    assignee_agent_id: str = "",
    unassign: bool = False,
    comment: str = "",
    project_id: str = "",
    goal_id: str = "",
    parent_id: str = "",
    billing_code: str = "",
    label_ids: list[str] | None = None,
    blocked_by_issue_ids: list[str] | None = None,
    review_policy: str = "",
    reopen: bool = False,
    resume: bool = False,
) -> Any:
    """Update an issue. Only provided fields change. Returns the issue plus a `changes` receipt.

    Args:
        issue_id: Issue UUID or identifier (e.g. "PAP-42").
        title: New title.
        description: New Markdown description.
        status: backlog, todo, in_progress, in_review, done, blocked or cancelled.
        priority: critical, high, medium or low.
        assignee_agent_id: Agent UUID or agent shortname (url key) in the same company.
        unassign: Set true to clear the assignee.
        comment: Comment posted atomically with the update. Required for review/approval
                 stage decisions (a separate comment call does not count).
        project_id: Move to this project UUID.
        goal_id: Link to this goal UUID.
        parent_id: Re-parent under this issue UUID.
        billing_code: Billing code.
        label_ids: Replace labels with these UUIDs.
        blocked_by_issue_ids: Replace blockers with these UUIDs ([] clears them).
        review_policy: anyone, not_creator or human_only.
        reopen: Reopen a done/blocked issue (moves it to todo).
        resume: Explicitly request follow-up on closed work; required to revive a cancelled issue.
    Note: with an agent API key, updating that agent's own in_progress issue needs a run id
    (401 otherwise).
    """
    body: dict[str, Any] = {}
    if title:
        body["title"] = title
    if description:
        body["description"] = description
    if status:
        body["status"] = check_enum(status, ISSUE_STATUSES, "status")
    if priority:
        body["priority"] = check_enum(priority, ISSUE_PRIORITIES, "priority")
    if unassign:
        body["assigneeAgentId"] = None
    elif assignee_agent_id:
        body["assigneeAgentId"] = assignee_agent_id
    if comment:
        body["comment"] = comment
    if project_id:
        body["projectId"] = project_id
    if goal_id:
        body["goalId"] = goal_id
    if parent_id:
        body["parentId"] = parent_id
    if billing_code:
        body["billingCode"] = billing_code
    if label_ids is not None:
        body["labelIds"] = label_ids
    if blocked_by_issue_ids is not None:
        body["blockedByIssueIds"] = blocked_by_issue_ids
    if review_policy:
        body["reviewPolicy"] = check_enum(review_policy, ISSUE_REVIEW_POLICIES, "review_policy")
    if reopen:
        body["reopen"] = True
    if resume:
        body["resume"] = True
    if not body:
        raise fail("No fields to update. Provide at least one field.")
    return await patch(f"/issues/{issue_id}", body)


@mcp.tool(tags={"issues"})
async def delete_issue(issue_id: str) -> Any:
    """Permanently delete an issue and its attachments. Cannot be undone; returns the deleted row.

    With an agent API key only unassigned or self-assigned issues can be deleted (403 otherwise).
    A 409 means a database constraint still references the issue.

    Args:
        issue_id: Issue UUID or identifier.
    """
    return await delete(f"/issues/{issue_id}")


# ── Checkout / release ─────────────────────────────────────────────────────────


@mcp.tool(tags={"issues"})
async def checkout_issue(
    issue_id: str,
    agent_id: str = "",
    expected_statuses: list[str] | None = None,
) -> Any:
    """Atomically claim an issue for an agent and move it to in_progress.

    Idempotent when the agent already owns it. 409 = another agent owns it, the project is
    paused, or a routine execution is active: do NOT retry. 422 = unresolved blockers.
    With an agent API key the agent can only check out as itself and needs a run id
    (PAPERCLIP_RUN_ID); a board API key can check out on behalf of any agent.

    Args:
        issue_id: Issue UUID or identifier.
        agent_id: Agent UUID to assign. Defaults to PAPERCLIP_AGENT_ID, then GET /agents/me.
        expected_statuses: Statuses the issue must currently be in. Default: todo, backlog,
                           blocked. Add "in_review" to pick up review work, or use
                           ["in_progress"] to re-claim after a crashed run.
    """
    statuses = check_enum_list(
        expected_statuses or list(CHECKOUT_DEFAULT_STATUSES), ISSUE_STATUSES, "expected_statuses"
    )
    body = {"agentId": await resolve_agent_id(agent_id), "expectedStatuses": statuses}
    return await post(f"/issues/{issue_id}/checkout", body)


@mcp.tool(tags={"issues"})
async def release_issue(issue_id: str) -> Any:
    """Release an issue: clears the assignee and checkout lock; in_progress issues return to todo.

    Only the assignee (or the owning checkout run) may release; 409 otherwise. With an agent
    API key a run id is required (401 without one); board keys need none.

    Args:
        issue_id: Issue UUID or identifier.
    """
    return await post(f"/issues/{issue_id}/release", {})


# ── Comments ───────────────────────────────────────────────────────────────────


@mcp.tool(tags={"issues"})
async def list_comments(
    issue_id: str,
    after: str = "",
    order: str = "desc",
    limit: int | None = None,
) -> Any:
    """List an issue's comments (Markdown bodies), newest first by default.

    Args:
        issue_id: Issue UUID or identifier.
        after: Comment UUID cursor; returns comments created after it (use with order="asc").
        order: "asc" or "desc". Default: desc.
        limit: Max comments (1-500). Omit for no cap.
    """
    check_enum(order, ("asc", "desc"), "order")
    params: dict[str, Any] = {"after": after, "order": order}
    if limit is not None:
        params["limit"] = clamp(limit, 1, 500)
    return await get(f"/issues/{issue_id}/comments", params)


@mcp.tool(tags={"issues"})
async def comment_on_issue(
    issue_id: str,
    body: str,
    reopen: bool = False,
    resume: bool = False,
    attachment_ids: list[str] | None = None,
    client_request_id: str = "",
) -> Any:
    """Add a Markdown comment to an issue. @AgentName mentions wake that agent.

    Args:
        issue_id: Issue UUID or identifier.
        body: Comment text (Markdown).
        reopen: Reopen a done or blocked issue (moves it to todo). Cancelled needs resume=true.
        resume: Explicitly request follow-up on closed/resumable work (revives cancelled issues).
        attachment_ids: Up to 20 attachment UUIDs already uploaded to this issue.
        client_request_id: UUID for safe retries (deduplicates the comment).
    """
    if not body.strip():
        raise fail("body must not be empty.")
    payload: dict[str, Any] = {"body": body}
    if reopen:
        payload["reopen"] = True
    if resume:
        payload["resume"] = True
    if attachment_ids:
        payload["attachmentIds"] = attachment_ids
    if client_request_id:
        payload["clientRequestId"] = client_request_id
    return await post(f"/issues/{issue_id}/comments", payload)


# ── Labels ─────────────────────────────────────────────────────────────────────


@mcp.tool(tags={"issues"})
async def list_labels() -> Any:
    """List the company's issue labels (id, name, color). Use ids with list_issues/create_issue."""
    return await get(company_path("/labels"))


# ── Documents ──────────────────────────────────────────────────────────────────


@mcp.tool(tags={"issues"})
async def list_documents(issue_id: str, include_system: bool = False) -> Any:
    """List an issue's revisioned documents (plan, design, notes ...) with latest revision ids.

    Args:
        issue_id: Issue UUID or identifier.
        include_system: Also include system documents (continuation-summary, pipeline-case-body).
    """
    return await get(
        f"/issues/{issue_id}/documents", {"includeSystem": "true" if include_system else None}
    )


@mcp.tool(tags={"issues"})
async def get_document(issue_id: str, key: str) -> Any:
    """Get one issue document (body + latestRevisionId) by key, e.g. "plan".

    Args:
        issue_id: Issue UUID or identifier.
        key: Document key: lowercase letters, digits, '-' or '_' (1-64 chars).
    """
    return await get(f"/issues/{issue_id}/documents/{key.strip().lower()}")


@mcp.tool(tags={"issues"})
async def upsert_document(
    issue_id: str,
    key: str,
    body: str,
    title: str = "",
    change_summary: str = "",
    base_revision_id: str = "",
) -> Any:
    """Create or update a Markdown issue document (e.g. the "plan"). Creates a new revision.

    Omit base_revision_id when creating; pass the current latestRevisionId when updating
    (a stale id returns 409). Returns 201 on create, 200 on update.

    Args:
        issue_id: Issue UUID or identifier.
        key: Document key (e.g. "plan", "design", "notes").
        body: Markdown content (max 512 KB).
        title: Optional document title (max 200 chars).
        change_summary: Optional revision note (max 500 chars).
        base_revision_id: latestRevisionId from get_document when updating.
    """
    payload: dict[str, Any] = {"format": "markdown", "body": body}
    if title:
        payload["title"] = title
    if change_summary:
        payload["changeSummary"] = change_summary
    if base_revision_id:
        payload["baseRevisionId"] = base_revision_id
    return await put(f"/issues/{issue_id}/documents/{key.strip().lower()}", payload)


# ── Interactions (structured cards in the issue thread) ────────────────────────


@mcp.tool(tags={"issues"})
async def list_interactions(issue_id: str) -> Any:
    """List issue-thread interactions (suggest_tasks, ask_user_questions, confirmations).

    Args:
        issue_id: Issue UUID or identifier.
    """
    return await get(f"/issues/{issue_id}/interactions")


@mcp.tool(tags={"issues"})
async def create_interaction(
    issue_id: str,
    kind: str,
    payload: dict[str, Any],
    title: str = "",
    summary: str = "",
    resolver_policy: str = "",
    continuation_policy: str = "",
    addressee_agent_id: str = "",
    idempotency_key: str = "",
) -> Any:
    """Create a structured interaction card on an issue thread (board key, or agent + run id).

    Args:
        issue_id: Issue UUID or identifier.
        kind: suggest_tasks, ask_user_questions, request_confirmation,
              request_checkbox_confirmation or request_item_verdicts.
        payload: Kind-specific payload with "version": 1. Examples:
                 request_confirmation -> {"version":1,"prompt":"Accept this plan?"};
                 ask_user_questions -> {"version":1,"questions":[{"id":"q1","prompt":"...",
                 "selectionMode":"single","options":[{"id":"a","label":"A"}]}]};
                 suggest_tasks -> {"version":1,"tasks":[{"clientKey":"t1","title":"..."}]}.
        title: Card title (max 240).
        summary: Card summary (max 1000).
        resolver_policy: anyone (default), not_creator or human_only.
        continuation_policy: none, wake_assignee or wake_assignee_on_accept.
        addressee_agent_id: Agent UUID that must resolve the card (it is woken).
        idempotency_key: Dedupe key (max 255).
    """
    body: dict[str, Any] = {"kind": check_enum(kind, INTERACTION_KINDS, "kind"), "payload": payload}
    if title:
        body["title"] = title
    if summary:
        body["summary"] = summary
    if resolver_policy:
        body["resolverPolicy"] = check_enum(
            resolver_policy, INTERACTION_RESOLVER_POLICIES, "resolver_policy"
        )
    if continuation_policy:
        body["continuationPolicy"] = check_enum(
            continuation_policy, INTERACTION_CONTINUATION_POLICIES, "continuation_policy"
        )
    if addressee_agent_id:
        body["addresseeAgentId"] = addressee_agent_id
    if idempotency_key:
        body["idempotencyKey"] = idempotency_key
    return await post(f"/issues/{issue_id}/interactions", body)


@mcp.tool(tags={"issues"})
async def accept_interaction(
    issue_id: str,
    interaction_id: str,
    selected_client_keys: list[str] | None = None,
    selected_option_ids: list[str] | None = None,
) -> Any:
    """Accept a pending interaction (confirmation, suggested tasks, checkbox confirmation).

    Args:
        issue_id: Issue UUID or identifier.
        interaction_id: Interaction UUID (see list_interactions).
        selected_client_keys: For suggest_tasks: subset of task clientKeys to accept.
        selected_option_ids: For request_checkbox_confirmation: chosen option ids.
    """
    body: dict[str, Any] = {}
    if selected_client_keys:
        body["selectedClientKeys"] = selected_client_keys
    if selected_option_ids:
        body["selectedOptionIds"] = selected_option_ids
    return await post(f"/issues/{issue_id}/interactions/{interaction_id}/accept", body)


@mcp.tool(tags={"issues"})
async def reject_interaction(issue_id: str, interaction_id: str, reason: str = "") -> Any:
    """Reject a pending interaction, optionally with a reason (required when the card demands one).

    Args:
        issue_id: Issue UUID or identifier.
        interaction_id: Interaction UUID.
        reason: Rejection reason (max 4000 chars).
    """
    body: dict[str, Any] = {"reason": reason} if reason else {}
    return await post(f"/issues/{issue_id}/interactions/{interaction_id}/reject", body)


@mcp.tool(tags={"issues"})
async def respond_to_interaction(
    issue_id: str,
    interaction_id: str,
    answers: list[dict[str, Any]],
    summary_markdown: str = "",
) -> Any:
    """Answer an ask_user_questions interaction.

    Args:
        issue_id: Issue UUID or identifier.
        interaction_id: Interaction UUID.
        answers: [{"questionId": "...", "optionIds": ["..."], "otherText": "..."}] (max 20).
        summary_markdown: Optional free-text summary (max 20000).
    """
    if not answers:
        raise fail("answers must contain at least one entry.")
    body: dict[str, Any] = {"answers": answers}
    if summary_markdown:
        body["summaryMarkdown"] = summary_markdown
    return await post(f"/issues/{issue_id}/interactions/{interaction_id}/respond", body)


# ── Diagnostics ────────────────────────────────────────────────────────────────


@mcp.tool(tags={"issues"})
async def get_issue_activity(issue_id: str) -> Any:
    """Audit trail for one issue (status changes, assignments, comments), newest first.

    Args:
        issue_id: Issue UUID or identifier.
    """
    return await get(f"/issues/{issue_id}/activity")


@mcp.tool(tags={"issues"})
async def get_issue_runs(issue_id: str) -> Any:
    """Heartbeat runs linked to an issue: status, error codes, liveness, token usage.
    Explains stuck or failed work.

    Args:
        issue_id: Issue UUID or identifier.
    """
    return await get(f"/issues/{issue_id}/runs")


@mcp.tool(tags={"issues"})
async def get_issue_cost_summary(issue_id: str, exclude_root: bool = False) -> Any:
    """Token spend, run count and runtime for an issue and all its descendants.

    Args:
        issue_id: Issue UUID or identifier.
        exclude_root: Count only descendants, not the issue itself.
    """
    return await get(
        f"/issues/{issue_id}/cost-summary", {"excludeRoot": "true" if exclude_root else None}
    )


@mcp.tool(tags={"issues"})
async def list_issue_approvals(issue_id: str) -> Any:
    """List approvals linked to an issue (the approvals gating this task).

    Args:
        issue_id: Issue UUID or identifier.
    """
    return await get(f"/issues/{issue_id}/approvals")
