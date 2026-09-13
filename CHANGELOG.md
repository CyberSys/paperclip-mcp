# Changelog

## 0.2.0 — 2026-09-13

Re-aligned with Paperclip `main` @ 2026-09-13 (package 0.3.1, release 2026.831). Audited every tool against the upstream route and zod schema sources.

### Breaking

- `PAPERCLIP_API_URL` replaces `PAPERCLIP_BASE_URL` (still accepted as an alias). `/api` is appended automatically.
- Priority `urgent` removed; valid priorities are `critical, high, medium, low`.
- `approve` / `reject` / `request_approval_revision` take `decision_note` (sent as `decisionNote`) instead of `comment`, whose value the server silently discarded.
- `list_issues`: `label` → `label_id` (server filter is `labelId`); default status set is now every open status including `backlog` and `in_review`.
- Tool failures are raised as MCP errors (`isError: true`) instead of being returned as `{"isError": true}` payloads.
- `PAPERCLIP_API_KEY` is no longer mandatory at startup (empty = local_trusted board operator); `PAPERCLIP_COMPANY_ID` still is.

### Fixed

- `checkout_issue` sent no body; the route requires `{agentId, expectedStatuses}` (400 before). Agent id resolves from the argument, `PAPERCLIP_AGENT_ID`, or `GET /agents/me`.
- `create_issue` sent `parentIssueId`; the field is `parentId`, so sub-issues were silently created at top level.
- `update_issue` rejected the valid statuses `backlog` / `in_review` and the priority `critical`.
- `list_approvals` rejected the valid status `cancelled`.
- 409 responses no longer get a hard-coded "already checked out" message; the server's error text, `code`, `details` and `remediation` are surfaced, plus hints for board-only / run-id failures.
- `Accept: application/json` is sent; `Content-Type` only with a body; `X-Paperclip-Run-Id` only on writes and only when `PAPERCLIP_RUN_ID` is set.
- Docstrings for `get_dashboard`, `get_cost_summary`, `list_activity`, `list_goals`, `release_issue` now describe the real response/semantics.

### Added

- 74 new tools: comments, labels, documents, interactions, heartbeat context, issue diagnostics; agent wake/pause/resume/terminate/hire/update, runs, budgets, keys, skills; goal/project CRUD; approval get/create/resubmit/comments; cost breakdowns, window spend, budget overview, attention feed, sidebar badges; routines; decisions; pipelines; `whoami`, `get_health`, `get_company`, `list_companies`, `create_board_api_key`, `list_secret_catalog`, `api_request`.
- Startup probe logs Paperclip version, deployment mode and whether the key is a board or agent key.
- Contract test suite (mocked HTTP) covering routes, bodies, enums and error mapping.
- Package split into `core.py` + one module per domain under `tools/`.

## 0.1.0

Initial release.
