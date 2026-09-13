# paperclip-mcp

MCP server for the [Paperclip](https://github.com/paperclipai/paperclip) AI agent orchestration platform, built for the **human operator**: run your company of agents from Claude Code, Claude Desktop or any MCP client.

Exposes the Paperclip REST API (v0.3.x, 2026-09) as 95 [Model Context Protocol](https://modelcontextprotocol.io) tools: issues, agents, goals, projects, approvals, costs and budgets, routines, decisions, pipelines and the attention feed.

> **Official MCP server vs this one.** Paperclip ships [`@paperclipai/mcp-server`](https://www.npmjs.com/package/@paperclipai/mcp-server) (TypeScript, stdio only, ~45 `paperclipXxx` tools) aimed at *agents running inside a heartbeat*. `paperclip-mcp` is the Python, HTTP-or-stdio server for the *board operator*: it adds wake/pause/resume, hiring, budgets, cost breakdowns, routines, decisions, pipelines and the attention feed, and understands board API keys. Use the official one for agents, this one for yourself.

---

## Tools

| Domain | Tools |
|---|---|
| **Identity & admin** | `whoami` · `get_health` · `get_company` · `list_companies` · `create_board_api_key` · `list_secret_catalog` · `api_request` (escape hatch for any `/api` endpoint) |
| **Issues** | `list_issues` · `get_issue` · `get_heartbeat_context` · `create_issue` · `update_issue` · `delete_issue` · `checkout_issue` · `release_issue` · `list_comments` · `comment_on_issue` · `list_labels` · `list_documents` · `get_document` · `upsert_document` · `list_interactions` · `create_interaction` · `accept_interaction` · `reject_interaction` · `respond_to_interaction` · `get_issue_activity` · `get_issue_runs` · `get_issue_cost_summary` · `list_issue_approvals` |
| **Agents** | `list_agents` · `get_agent` · `get_my_inbox` · `list_company_skills` · `wake_agent` · `invoke_agent_heartbeat` (legacy) · `pause_agent` · `resume_agent` · `clear_agent_error` · `terminate_agent` · `approve_agent` · `create_agent` · `create_agent_hire` · `update_agent` · `set_agent_budget` · `create_agent_api_key` · `list_agent_runs` · `get_run` · `cancel_run` · `list_live_runs` |
| **Goals & projects** | `list_goals` · `get_goal` · `create_goal` · `update_goal` · `delete_goal` · `list_projects` · `get_project` · `create_project` · `update_project` |
| **Approvals** | `list_approvals` · `get_approval` · `create_approval` · `approve` · `reject` · `request_approval_revision` · `resubmit_approval` · `list_approval_issues` · `list_approval_comments` · `add_approval_comment` |
| **Monitoring** | `get_dashboard` · `get_cost_summary` · `get_cost_breakdown` · `get_cost_window_spend` · `get_budget_overview` · `set_company_budget` · `list_activity` · `get_attention_feed` · `get_sidebar_badges` |
| **Routines** | `list_routines` · `get_routine` · `create_routine` · `update_routine` · `run_routine` · `list_routine_runs` · `create_routine_trigger` |
| **Decisions** | `list_decisions` · `get_decision` · `decide_decision` · `dismiss_decision` |
| **Pipelines** | `list_pipelines` · `get_pipeline` · `list_pipeline_attention` · `list_pipeline_cases` · `ingest_pipeline_case` · `review_pipeline_case` |

Issue ids accept either the UUID or the human identifier (`PAP-42`). Every tool docstring states which credential it needs.

---

## Requirements

- Python 3.10+
- A running Paperclip instance (tested against `main` @ 2026-09-13, package version 0.3.1 / release 2026.831)
- A **board API key** (recommended) or an agent API key — see [Credentials](#credentials)

---

## Installation

```bash
git clone https://github.com/wizarck/paperclip-mcp
cd paperclip-mcp
pip install -e .          # or: uv pip install -e .
```

---

## Configuration

Copy `.env.example` to `.env` and fill in the values (never commit `.env`):

```dotenv
PAPERCLIP_API_URL=http://localhost:3100   # "/api" is appended automatically
PAPERCLIP_API_KEY=pcp_board_...           # board key (recommended) or agent key
PAPERCLIP_COMPANY_ID=your_company_uuid    # from the UI URL /companies/{uuid}
PAPERCLIP_AGENT_ID=                       # optional: default agent for checkout_issue
PAPERCLIP_RUN_ID=                         # optional: real heartbeat run id, never invent one
```

`PAPERCLIP_BASE_URL` (0.1.x) is still accepted as an alias of `PAPERCLIP_API_URL`.

### Credentials

Paperclip resolves a bearer token as a **board API key** first, then as an **agent API key**. What you can do depends on which one you configure:

| Capability | Board key `pcp_board_…` | Agent key |
|---|---|---|
| Read issues, agents, goals, projects, costs, dashboard, activity | ✅ | ✅ (own company) |
| Create / update issues, comments, documents, goals, projects | ✅ | ✅ |
| `checkout_issue` / `release_issue` | ✅ any agent | only itself, and needs `PAPERCLIP_RUN_ID` |
| `approve` / `reject` / `request_approval_revision` | ✅ | ❌ 403 |
| `pause_agent` / `terminate_agent` / `clear_agent_error` / budgets / API keys | ✅ | ❌ 403 |
| `get_attention_feed`, decisions, `list_companies` | ✅ | ❌ 403 |
| `get_agent("me")`, `get_my_inbox` | ❌ 401 | ✅ |

**Getting a board key**

- CLI: `paperclipai login` mints one, or
- API: `POST /api/board-api-keys` from a logged-in board session, or
- On a `local_trusted` deployment: start this server with an empty `PAPERCLIP_API_KEY` (requests act as the local board operator) and call the `create_board_api_key` tool.

Run `whoami` in your MCP client to confirm which credential is active; the server also logs it at startup.

---

## Usage

```bash
paperclip-mcp                          # streamable-http on http://127.0.0.1:9011/mcp
paperclip-mcp --port 9012
paperclip-mcp --transport stdio        # for Claude Desktop
paperclip-mcp --help
```

### Claude Code

```bash
claude mcp add paperclip --transport http http://localhost:9011/mcp
```

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "paperclip": {
      "command": "paperclip-mcp",
      "args": ["--transport", "stdio"],
      "env": {
        "PAPERCLIP_API_URL": "http://localhost:3100",
        "PAPERCLIP_API_KEY": "pcp_board_...",
        "PAPERCLIP_COMPANY_ID": "your_company_uuid"
      }
    }
  }
}
```

### Auto-start with your MCP stack

```bash
curl -s --max-time 1 http://localhost:9011/mcp > /dev/null 2>&1 || \
  nohup paperclip-mcp > /tmp/paperclip-mcp.log 2>&1 &
```

---

## Example interactions

```
"What needs my attention?"
→ get_attention_feed()   (board key)  /  get_sidebar_badges() + list_approvals()

"What is the Purchasing agent working on?"
→ list_issues(assignee_agent_id="...")

"Create a critical task for the CEO to find cheese suppliers in Barcelona, under PAP-12"
→ create_issue(title=..., priority="critical", assignee_agent_id="...", parent_issue_id="PAP-12")

"Mark PAP-42 done and leave a note"
→ update_issue(issue_id="PAP-42", status="done", comment="Verified in staging.")

"Approve the pending hire"
→ list_approvals() + approve(approval_id="...", decision_note="Go ahead")

"Which agent is burning the budget this week?"
→ get_cost_window_spend() + get_cost_breakdown(group_by="agent")

"Pause the Marketing agent and cancel its current run"
→ list_live_runs() + cancel_run(run_id="...") + pause_agent(agent_id="...")

"Run the weekly briefing routine now"
→ list_routines() + run_routine(routine_id="...")
```

---

## Behaviour worth knowing

- **Enums are validated client-side** before any request: statuses `backlog, todo, in_progress, in_review, done, blocked, cancelled`; priorities `critical, high, medium, low` (there is no `urgent`).
- **`list_issues` defaults to open statuses** (everything except `done`/`cancelled`). Pass `status=""` for all.
- **`checkout_issue` sends the required body** `{agentId, expectedStatuses}`; the agent comes from the argument, then `PAPERCLIP_AGENT_ID`, then `GET /agents/me`.
- **Errors are real MCP errors** (`isError: true`) carrying the server's message, `code`, `details` and a hint, e.g. *"Board access required → configure a board API key"*. A `409` means the state changed under you (conflict, paused project, stale revision): do not blindly retry.
- **`X-Paperclip-Run-Id` is only sent when `PAPERCLIP_RUN_ID` is set**, and only on writes. A fabricated run id violates a foreign key server-side.
- **`api_request`** lets you call any `/api` route that has no dedicated tool (`{company}` in the path expands to the configured company).

---

## Development

```bash
pip install -e ".[dev]"
ruff check src/ tests/ && ruff format --check src/ tests/
mypy src/
pytest            # contract tests against a mocked Paperclip API
```

Layout: `src/paperclip_mcp/core.py` (config, HTTP client, errors, enums, FastMCP instance) and one module per domain under `src/paperclip_mcp/tools/`.

---

## Architecture notes

- **Who should use this MCP**: human operators managing agents via Claude Code / Claude Desktop, with a board API key.
- **Do agents need this MCP?** No. Agents talk to the REST API directly during their heartbeat, and Paperclip ships `@paperclipai/mcp-server` for agent-side MCP access. If you switch to [Hermes](https://github.com/NousResearch/hermes-paperclip-adapter), either MCP works since Hermes supports MCP natively.
- **Transport**: `streamable-http` for Claude Code and mcp-proxy; `stdio` for Claude Desktop.
- **Security**: binds to `127.0.0.1` by default and carries your Paperclip key. Do not expose it publicly.

---

## License

MIT — see [LICENSE](LICENSE).
