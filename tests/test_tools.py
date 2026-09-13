"""Contract tests: every tool must hit the Paperclip v0.3.x route with the right shape."""

from __future__ import annotations

import httpx

from paperclip_mcp import core
from tests.conftest import AGENT, COMPANY, Recorder, call, call_error

# ── Surface ────────────────────────────────────────────────────────────────────


async def test_tool_surface(client) -> None:
    tools = {t.name for t in await client.list_tools()}
    expected = {
        "whoami",
        "get_health",
        "api_request",
        "list_issues",
        "get_issue",
        "create_issue",
        "update_issue",
        "delete_issue",
        "checkout_issue",
        "release_issue",
        "list_comments",
        "comment_on_issue",
        "list_labels",
        "list_documents",
        "get_document",
        "upsert_document",
        "list_agents",
        "get_agent",
        "wake_agent",
        "pause_agent",
        "resume_agent",
        "create_agent",
        "update_agent",
        "list_agent_runs",
        "list_goals",
        "create_goal",
        "update_goal",
        "list_projects",
        "create_project",
        "list_approvals",
        "approve",
        "reject",
        "request_approval_revision",
        "get_dashboard",
        "get_cost_summary",
        "get_cost_breakdown",
        "list_activity",
        "get_attention_feed",
        "list_routines",
        "run_routine",
        "list_decisions",
        "decide_decision",
        "list_pipelines",
    }
    missing = expected - tools
    assert not missing, f"missing tools: {sorted(missing)}"
    assert len(tools) >= 80


# ── Headers / client conventions ───────────────────────────────────────────────


async def test_get_headers(client, recorder: Recorder) -> None:
    await call(client, "get_dashboard")
    req = recorder.last
    assert req.method == "GET"
    assert req.url.path == f"/api/companies/{COMPANY}/dashboard"
    assert req.headers["Authorization"] == "Bearer pcp_board_testkey"
    assert req.headers["Accept"] == "application/json"
    assert "Content-Type" not in req.headers
    assert "X-Paperclip-Run-Id" not in req.headers


async def test_run_id_only_on_writes(client, recorder: Recorder, monkeypatch) -> None:
    monkeypatch.setattr(core, "RUN_ID", "33333333-3333-3333-3333-333333333333")
    await call(client, "get_issue", issue_id="PAP-1")
    assert "X-Paperclip-Run-Id" not in recorder.last.headers
    await call(client, "comment_on_issue", issue_id="PAP-1", body="hi")
    assert recorder.last.headers["X-Paperclip-Run-Id"] == "33333333-3333-3333-3333-333333333333"
    assert recorder.last.headers["Content-Type"] == "application/json"


def test_api_url_normalization() -> None:
    assert core.normalize_api_url("http://localhost:3100") == "http://localhost:3100/api"
    assert core.normalize_api_url("http://localhost:3100/") == "http://localhost:3100/api"
    assert core.normalize_api_url("http://localhost:3100/api/") == "http://localhost:3100/api"


# ── Error mapping ──────────────────────────────────────────────────────────────


async def test_server_error_surfaces_message_code_and_hint(client, recorder: Recorder) -> None:
    recorder.respond(
        lambda r: (
            httpx.Response(403, json={"error": "Board access required", "code": "FORBIDDEN"})
            if r.url.path.endswith("/approve")
            else None
        )
    )
    text = await call_error(client, "approve", approval_id="a1")
    assert "HTTP 403" in text and "Board access required" in text
    assert "code=FORBIDDEN" in text
    assert "board API key" in text  # hint


async def test_409_keeps_server_text(client, recorder: Recorder) -> None:
    recorder.respond(
        lambda r: (
            httpx.Response(409, json={"error": "Project is paused"})
            if r.url.path.endswith("/checkout")
            else None
        )
    )
    text = await call_error(client, "checkout_issue", issue_id="PAP-2")
    assert "Project is paused" in text and "409" in text
    assert "already checked out" not in text


async def test_validation_error_details(client, recorder: Recorder) -> None:
    recorder.respond(
        lambda r: httpx.Response(
            400, json={"error": "Validation error", "details": [{"path": ["priority"]}]}
        )
    )
    text = await call_error(client, "create_issue", title="x")
    assert "Validation error" in text and "priority" in text


async def test_empty_204_becomes_ok(client, recorder: Recorder) -> None:
    recorder.respond(lambda r: httpx.Response(204))
    assert await call(client, "delete_issue", issue_id="PAP-3") == {"ok": True}


# ── Issues ─────────────────────────────────────────────────────────────────────


async def test_list_issues_params(client, recorder: Recorder) -> None:
    await call(
        client,
        "list_issues",
        label_id="lab-1",
        q="cheese",
        limit=5000,
        compact=True,
        assignee_agent_id="null",
    )
    params = dict(recorder.last.url.params)
    assert params["labelId"] == "lab-1"
    assert "label" not in params
    assert params["q"] == "cheese"
    assert params["limit"] == "1000"
    assert params["view"] == "compact"
    assert params["assigneeAgentId"] == "null"
    assert params["status"] == "backlog,todo,in_progress,in_review,blocked"


async def test_list_issues_rejects_unknown_status(client) -> None:
    text = await call_error(client, "list_issues", status="todo,urgent")
    assert "Invalid status 'urgent'" in text


async def test_create_issue_body(client, recorder: Recorder) -> None:
    await call(
        client,
        "create_issue",
        title="T",
        parent_issue_id="p-1",
        priority="critical",
        status="in_review",
        goal_id="g-1",
        label_ids=["l1"],
        blocked_by_issue_ids=["b1"],
    )
    assert recorder.last.url.path == f"/api/companies/{COMPANY}/issues"
    body = recorder.body()
    assert body["parentId"] == "p-1"
    assert "parentIssueId" not in body
    assert body["priority"] == "critical"
    assert body["status"] == "in_review"
    assert body["goalId"] == "g-1"
    assert body["labelIds"] == ["l1"]
    assert body["blockedByIssueIds"] == ["b1"]


async def test_create_issue_rejects_urgent(client) -> None:
    text = await call_error(client, "create_issue", title="T", priority="urgent")
    assert "critical, high, medium, low" in text


async def test_update_issue_body(client, recorder: Recorder) -> None:
    await call(
        client,
        "update_issue",
        issue_id="PAP-4",
        status="backlog",
        priority="critical",
        unassign=True,
        comment="done",
        blocked_by_issue_ids=[],
        resume=True,
    )
    req = recorder.last
    assert req.method == "PATCH" and req.url.path == "/api/issues/PAP-4"
    body = recorder.body()
    assert body == {
        "status": "backlog",
        "priority": "critical",
        "assigneeAgentId": None,
        "comment": "done",
        "blockedByIssueIds": [],
        "resume": True,
    }


async def test_update_issue_requires_a_field(client) -> None:
    assert "No fields to update" in await call_error(client, "update_issue", issue_id="PAP-4")


async def test_checkout_issue_sends_required_body(client, recorder: Recorder) -> None:
    await call(client, "checkout_issue", issue_id="PAP-5")
    assert recorder.last.method == "POST"
    assert recorder.last.url.path == "/api/issues/PAP-5/checkout"
    assert recorder.body() == {"agentId": AGENT, "expectedStatuses": ["todo", "backlog", "blocked"]}


async def test_checkout_issue_custom_statuses_and_agent(client, recorder: Recorder) -> None:
    await call(
        client,
        "checkout_issue",
        issue_id="PAP-5",
        agent_id="other",
        expected_statuses=["in_progress"],
    )
    assert recorder.body() == {"agentId": "other", "expectedStatuses": ["in_progress"]}


async def test_checkout_issue_resolves_agent_via_me(
    client, recorder: Recorder, monkeypatch
) -> None:
    monkeypatch.setattr(core, "AGENT_ID", "")
    recorder.respond(
        lambda r: (
            httpx.Response(200, json={"id": "me-id"}) if r.url.path == "/api/agents/me" else None
        )
    )
    await call(client, "checkout_issue", issue_id="PAP-5")
    assert [r.url.path for r in recorder.requests] == [
        "/api/agents/me",
        "/api/issues/PAP-5/checkout",
    ]
    assert recorder.body()["agentId"] == "me-id"


async def test_create_issue_allow_duplicate_and_heartbeat_context(
    client, recorder: Recorder
) -> None:
    await call(client, "create_issue", title="T", allow_duplicate=True)
    assert recorder.body()["allowDuplicate"] is True
    await call(client, "create_issue", title="T")
    assert "allowDuplicate" not in recorder.body()
    await call(client, "get_heartbeat_context", issue_id="PAP-1", wake_comment_id="c1")
    assert recorder.last.url.path == "/api/issues/PAP-1/heartbeat-context"
    assert dict(recorder.last.url.params) == {"wakeCommentId": "c1"}


async def test_wake_agent_me_resolves_configured_agent(client, recorder: Recorder) -> None:
    await call(client, "wake_agent", agent_id="me")
    assert recorder.last.url.path == f"/api/agents/{AGENT}/wakeup"
    await call(client, "invoke_agent_heartbeat", agent_id="ME", reason="go")
    assert recorder.last.url.path == f"/api/agents/{AGENT}/heartbeat/invoke"
    assert recorder.body() == {"reason": "go"}


def test_validate_config_rejects_non_uuid_run_id(monkeypatch) -> None:
    import pytest

    monkeypatch.setattr(core, "RUN_ID", "not-a-uuid")
    with pytest.raises(SystemExit):
        core.validate_config()


async def test_error_extra_body_fields_are_surfaced(client, recorder: Recorder) -> None:
    recorder.respond(
        lambda r: httpx.Response(
            422,
            json={"error": "Run id mismatch", "code": "agent_jwt_run_id_mismatch", "reason": "x"},
        )
    )
    text = await call_error(client, "release_issue", issue_id="PAP-6")
    assert "code=agent_jwt_run_id_mismatch" in text and "'reason': 'x'" in text


async def test_release_issue_sends_empty_object(client, recorder: Recorder) -> None:
    await call(client, "release_issue", issue_id="PAP-6")
    assert recorder.last.url.path == "/api/issues/PAP-6/release"
    assert recorder.body() == {}


async def test_comment_on_issue(client, recorder: Recorder) -> None:
    await call(
        client, "comment_on_issue", issue_id="PAP-7", body="x", reopen=True, attachment_ids=["att"]
    )
    assert recorder.body() == {"body": "x", "reopen": True, "attachmentIds": ["att"]}
    assert "empty" in await call_error(client, "comment_on_issue", issue_id="PAP-7", body="  ")


async def test_list_comments_params(client, recorder: Recorder) -> None:
    await call(client, "list_comments", issue_id="PAP-7", after="c1", order="asc", limit=9999)
    params = dict(recorder.last.url.params)
    assert params == {"after": "c1", "order": "asc", "limit": "500"}


async def test_documents(client, recorder: Recorder) -> None:
    await call(
        client,
        "upsert_document",
        issue_id="PAP-8",
        key="Plan",
        body="# hi",
        base_revision_id="rev-1",
    )
    assert recorder.last.method == "PUT"
    assert recorder.last.url.path == "/api/issues/PAP-8/documents/plan"
    assert recorder.body() == {"format": "markdown", "body": "# hi", "baseRevisionId": "rev-1"}
    await call(client, "list_documents", issue_id="PAP-8", include_system=True)
    assert dict(recorder.last.url.params) == {"includeSystem": "true"}


async def test_interactions(client, recorder: Recorder) -> None:
    await call(
        client,
        "create_interaction",
        issue_id="PAP-9",
        kind="request_confirmation",
        payload={"version": 1, "prompt": "ok?"},
        resolver_policy="human_only",
    )
    body = recorder.body()
    assert body["kind"] == "request_confirmation" and body["resolverPolicy"] == "human_only"
    await call(
        client,
        "accept_interaction",
        issue_id="PAP-9",
        interaction_id="i1",
        selected_client_keys=["t1"],
    )
    assert recorder.last.url.path == "/api/issues/PAP-9/interactions/i1/accept"
    assert recorder.body() == {"selectedClientKeys": ["t1"]}
    assert "Invalid kind" in await call_error(
        client, "create_interaction", issue_id="PAP-9", kind="connection_intent", payload={}
    )


async def test_issue_diagnostics_paths(client, recorder: Recorder) -> None:
    await call(client, "get_issue_activity", issue_id="PAP-1")
    assert recorder.last.url.path == "/api/issues/PAP-1/activity"
    await call(client, "get_issue_runs", issue_id="PAP-1")
    assert recorder.last.url.path == "/api/issues/PAP-1/runs"
    await call(client, "get_issue_cost_summary", issue_id="PAP-1", exclude_root=True)
    assert recorder.last.url.path == "/api/issues/PAP-1/cost-summary"
    assert dict(recorder.last.url.params) == {"excludeRoot": "true"}
    await call(client, "list_labels")
    assert recorder.last.url.path == f"/api/companies/{COMPANY}/labels"


# ── Agents ─────────────────────────────────────────────────────────────────────


async def test_agents_read(client, recorder: Recorder) -> None:
    await call(client, "list_agents")
    assert recorder.last.url.path == f"/api/companies/{COMPANY}/agents"
    assert not dict(recorder.last.url.params)  # any query param -> 400 upstream
    await call(client, "get_agent")
    assert recorder.last.url.path == "/api/agents/me"
    await call(client, "get_agent", agent_id="ceo", company_id=COMPANY)
    assert recorder.last.url.path == "/api/agents/ceo"
    assert dict(recorder.last.url.params) == {"companyId": COMPANY}


async def test_wake_agent_always_sends_object_body(client, recorder: Recorder) -> None:
    await call(client, "wake_agent", agent_id="a1")
    assert recorder.last.url.path == "/api/agents/a1/wakeup"
    assert recorder.body() == {"source": "on_demand", "triggerDetail": "manual"}
    await call(
        client, "wake_agent", agent_id="a1", reason="go", payload={"k": 1}, force_fresh_session=True
    )
    body = recorder.body()
    assert (
        body["reason"] == "go" and body["payload"] == {"k": 1} and body["forceFreshSession"] is True
    )


async def test_agent_lifecycle_paths(client, recorder: Recorder) -> None:
    for tool, suffix in [
        ("pause_agent", "pause"),
        ("resume_agent", "resume"),
        ("clear_agent_error", "clear-error"),
        ("terminate_agent", "terminate"),
        ("approve_agent", "approve"),
    ]:
        await call(client, tool, agent_id="a1")
        assert recorder.last.method == "POST"
        assert recorder.last.url.path == f"/api/agents/a1/{suffix}"


async def test_create_and_update_agent(client, recorder: Recorder) -> None:
    await call(
        client,
        "create_agent",
        name="Bob",
        role="engineer",
        reports_to="boss",
        budget_monthly_cents=500,
        adapter_config={"model": "x"},
    )
    assert recorder.last.url.path == f"/api/companies/{COMPANY}/agents"
    body = recorder.body()
    assert body["adapterType"] == "claude_local" and body["role"] == "engineer"
    assert body["reportsTo"] == "boss" and body["budgetMonthlyCents"] == 500
    await call(client, "create_agent_hire", name="Ann", source_issue_ids=["i1"])
    assert recorder.last.url.path == f"/api/companies/{COMPANY}/agent-hires"
    assert recorder.body()["sourceIssueIds"] == ["i1"]
    await call(
        client,
        "update_agent",
        agent_id="a1",
        status="paused",
        adapter_config={"m": 1},
        replace_adapter_config=True,
    )
    assert recorder.last.method == "PATCH" and recorder.last.url.path == "/api/agents/a1"
    assert recorder.body() == {
        "status": "paused",
        "adapterConfig": {"m": 1},
        "replaceAdapterConfig": True,
    }
    assert "Invalid role" in await call_error(client, "create_agent", name="x", role="wizard")


async def test_runs_and_budget(client, recorder: Recorder) -> None:
    await call(client, "list_agent_runs", agent_id="a1", limit=10)
    assert recorder.last.url.path == f"/api/companies/{COMPANY}/heartbeat-runs"
    assert dict(recorder.last.url.params) == {"agentId": "a1", "limit": "10", "summary": "true"}
    await call(client, "get_run", run_id="r1")
    assert recorder.last.url.path == "/api/heartbeat-runs/r1"
    await call(client, "cancel_run", run_id="r1")
    assert recorder.last.url.path == "/api/heartbeat-runs/r1/cancel"
    await call(client, "set_agent_budget", agent_id="a1", budget_monthly_cents=1000)
    assert recorder.last.method == "PATCH" and recorder.last.url.path == "/api/agents/a1/budgets"
    assert recorder.body() == {"budgetMonthlyCents": 1000}


# ── Goals & projects ───────────────────────────────────────────────────────────


async def test_goals(client, recorder: Recorder) -> None:
    await call(client, "create_goal", title="Win")
    assert recorder.body() == {"title": "Win", "level": "company", "status": "active"}
    await call(client, "update_goal", goal_id="g1", status="achieved")
    assert recorder.last.method == "PATCH" and recorder.last.url.path == "/api/goals/g1"
    assert recorder.body() == {"status": "achieved"}
    assert "Invalid status" in await call_error(client, "update_goal", goal_id="g1", status="done")
    await call(client, "delete_goal", goal_id="g1")
    assert recorder.last.method == "DELETE"


async def test_projects(client, recorder: Recorder) -> None:
    await call(client, "list_projects", include_archived=True)
    assert recorder.last.url.path == f"/api/companies/{COMPANY}/projects"
    assert dict(recorder.last.url.params) == {"includeArchived": "true"}
    await call(
        client,
        "create_project",
        name="P",
        status="planned",
        goal_ids=["g1"],
        workspace_repo_url="https://x/y.git",
        workspace_repo_ref="main",
    )
    body = recorder.body()
    assert body["status"] == "planned" and body["goalIds"] == ["g1"]
    assert body["workspace"] == {"isPrimary": True, "repoUrl": "https://x/y.git", "repoRef": "main"}
    await call(client, "update_project", project_id="p1", archived=True)
    assert recorder.body()["archivedAt"].endswith("Z")
    await call(client, "update_project", project_id="p1", archived=False)
    assert recorder.body() == {"archivedAt": None}


# ── Approvals ──────────────────────────────────────────────────────────────────


async def test_list_approvals_statuses(client, recorder: Recorder) -> None:
    await call(client, "list_approvals", status="cancelled")
    assert dict(recorder.last.url.params) == {"status": "cancelled"}
    await call(client, "list_approvals", status="")
    assert not dict(recorder.last.url.params)
    assert "Invalid status" in await call_error(client, "list_approvals", status="nope")


async def test_approval_decisions_use_decision_note(client, recorder: Recorder) -> None:
    await call(client, "approve", approval_id="ap1", decision_note="ok")
    assert recorder.last.url.path == "/api/approvals/ap1/approve"
    assert recorder.body() == {"decisionNote": "ok"}
    await call(client, "reject", approval_id="ap1")
    assert recorder.body() == {}
    await call(client, "request_approval_revision", approval_id="ap1", decision_note="fix")
    assert recorder.last.url.path == "/api/approvals/ap1/request-revision"
    assert recorder.body() == {"decisionNote": "fix"}
    assert "required" in await call_error(
        client, "request_approval_revision", approval_id="ap1", decision_note=" "
    )
    await call(client, "resubmit_approval", approval_id="ap1", payload={"a": 1})
    assert recorder.body() == {"payload": {"a": 1}}


async def test_create_approval(client, recorder: Recorder) -> None:
    await call(client, "create_approval", type="request_board_approval", issue_ids=["i1"])
    assert recorder.last.url.path == f"/api/companies/{COMPANY}/approvals"
    assert recorder.body() == {"type": "request_board_approval", "payload": {}, "issueIds": ["i1"]}
    assert "Invalid type" in await call_error(client, "create_approval", type="hire")


# ── Monitoring ─────────────────────────────────────────────────────────────────


async def test_costs(client, recorder: Recorder) -> None:
    await call(client, "get_cost_summary", from_date="2026-09-01")
    assert recorder.last.url.path == f"/api/companies/{COMPANY}/costs/summary"
    assert dict(recorder.last.url.params) == {"from": "2026-09-01"}
    await call(client, "get_cost_breakdown", group_by="agent_model")
    assert recorder.last.url.path == f"/api/companies/{COMPANY}/costs/by-agent-model"
    await call(client, "get_cost_breakdown")
    assert recorder.last.url.path == f"/api/companies/{COMPANY}/costs/by-agent"
    await call(client, "set_company_budget", budget_monthly_cents=100)
    assert recorder.last.method == "PATCH"
    assert recorder.last.url.path == f"/api/companies/{COMPANY}/budgets"
    assert recorder.body() == {"budgetMonthlyCents": 100}


async def test_activity_and_attention(client, recorder: Recorder) -> None:
    await call(client, "list_activity", entity_type="issue", entity_id="u1", limit=9999)
    assert dict(recorder.last.url.params) == {
        "entityType": "issue",
        "entityId": "u1",
        "limit": "500",
    }
    await call(client, "get_attention_feed", sort="decide", include_dismissed=True)
    assert recorder.last.url.path == f"/api/companies/{COMPANY}/attention"
    assert dict(recorder.last.url.params) == {
        "limit": "50",
        "sort": "decide",
        "includeDismissed": "true",
    }
    await call(client, "get_sidebar_badges")
    assert recorder.last.url.path == f"/api/companies/{COMPANY}/sidebar-badges"


# ── Routines / decisions / pipelines ───────────────────────────────────────────


async def test_routines(client, recorder: Recorder) -> None:
    await call(client, "create_routine", title="Weekly", assignee_agent_id="a1")
    assert recorder.last.url.path == f"/api/companies/{COMPANY}/routines"
    body = recorder.body()
    assert body["priority"] == "medium" and body["status"] == "active"
    assert body["concurrencyPolicy"] == "coalesce_if_active"
    await call(client, "update_routine", routine_id="r1", status="paused", base_revision_id="rev")
    assert recorder.body() == {"status": "paused", "baseRevisionId": "rev"}
    await call(client, "run_routine", routine_id="r1", payload={"x": 1})
    assert recorder.last.url.path == "/api/routines/r1/run"
    assert recorder.body() == {"source": "manual", "payload": {"x": 1}}
    await call(
        client,
        "create_routine_trigger",
        routine_id="r1",
        kind="schedule",
        cron_expression="0 9 * * 1",
        timezone="Europe/Madrid",
    )
    assert recorder.body() == {
        "kind": "schedule",
        "enabled": True,
        "cronExpression": "0 9 * * 1",
        "timezone": "Europe/Madrid",
    }
    assert "cron_expression" in await call_error(
        client, "create_routine_trigger", routine_id="r1", kind="schedule"
    )


async def test_decisions(client, recorder: Recorder) -> None:
    await call(client, "list_decisions")
    assert recorder.last.url.path == f"/api/companies/{COMPANY}/decisions"
    assert dict(recorder.last.url.params) == {"status": "open", "limit": "50"}
    await call(client, "decide_decision", decision_id="d1", option_id="o1", input_values={"a": "b"})
    assert recorder.last.url.path == "/api/decisions/d1/decide"
    assert recorder.body() == {"optionId": "o1", "inputValues": {"a": "b"}}


async def test_pipelines(client, recorder: Recorder) -> None:
    await call(client, "list_pipeline_cases", pipeline_id="p1", stage_key="review", terminal=False)
    assert recorder.last.url.path == "/api/pipelines/p1/cases"
    assert dict(recorder.last.url.params) == {"stageKey": "review", "terminal": "false"}
    await call(client, "ingest_pipeline_case", pipeline_id="p1", title="Lead", case_key="k1")
    assert recorder.body() == {"title": "Lead", "caseKey": "k1"}
    await call(client, "review_pipeline_case", case_id="c1", decision="approve", expected_version=3)
    assert recorder.last.url.path == "/api/cases/c1/review"
    assert recorder.body() == {"decision": "approve", "expectedVersion": 3}


# ── Admin ──────────────────────────────────────────────────────────────────────


async def test_whoami_board(client, recorder: Recorder) -> None:
    recorder.respond(
        lambda r: (
            httpx.Response(200, json={"userId": "u1"}) if r.url.path == "/api/cli-auth/me" else None
        )
    )
    assert (await call(client, "whoami"))["actorType"] == "board"


async def test_whoami_falls_back_to_agent(client, recorder: Recorder) -> None:
    def responder(r: httpx.Request) -> httpx.Response | None:
        if r.url.path == "/api/cli-auth/me":
            return httpx.Response(401, json={"error": "Board authentication required"})
        if r.url.path == "/api/agents/me":
            return httpx.Response(200, json={"id": "a1", "name": "CEO"})
        return None

    recorder.respond(responder)
    result = await call(client, "whoami")
    assert result["actorType"] == "agent" and result["name"] == "CEO"


async def test_api_request_escape_hatch(client, recorder: Recorder) -> None:
    await call(
        client,
        "api_request",
        method="post",
        path="/companies/{company}/org",
        body={"a": 1},
        params={"q": "z"},
    )
    assert recorder.last.method == "POST"
    assert recorder.last.url.path == f"/api/companies/{COMPANY}/org"
    assert dict(recorder.last.url.params) == {"q": "z"}
    assert recorder.body() == {"a": 1}
    assert "must start with" in await call_error(client, "api_request", method="GET", path="../x")


async def test_create_board_api_key(client, recorder: Recorder) -> None:
    await call(client, "create_board_api_key")
    assert recorder.last.url.path == "/api/board-api-keys"
    assert recorder.body() == {"name": "paperclip-mcp", "requestedCompanyId": COMPANY}
