"""
Shared runtime for paperclip-mcp: configuration, HTTP client, error mapping,
enum constants and the FastMCP server instance that tool modules register on.

Configuration (environment variables):
    PAPERCLIP_API_URL      Paperclip base URL. "/api" is appended when missing.
                           Default: http://localhost:3100  (PAPERCLIP_BASE_URL is
                           accepted as a legacy alias.)
    PAPERCLIP_API_KEY      Bearer token. Either a BOARD API key (pcp_board_..., minted
                           with POST /api/board-api-keys or the CLI login) or an AGENT
                           API key (POST /api/agents/{id}/keys). Board keys unlock the
                           operator-only tools (approve/reject, pause agents, budgets,
                           attention feed, decisions). Optional only for local_trusted
                           deployments, where a request without a token is treated as
                           the local board operator.
    PAPERCLIP_COMPANY_ID   Required. Company UUID all company-scoped tools operate on.
    PAPERCLIP_AGENT_ID     Optional. Default agentId for checkout_issue when the key is
                           a board key (agent keys resolve it via GET /agents/me).
    PAPERCLIP_RUN_ID       Optional. Forwarded as X-Paperclip-Run-Id on write requests.
                           Must be a real heartbeat run id; never fabricate one.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional
    pass

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] paperclip-mcp %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stderr,
)
log = logging.getLogger("paperclip_mcp")
logging.getLogger("httpx").setLevel(logging.WARNING)

# ── Configuration ──────────────────────────────────────────────────────────────


def normalize_api_url(raw: str) -> str:
    """Strip trailing slashes and append '/api' when absent (mirrors the official MCP)."""
    trimmed = raw.strip().rstrip("/")
    return trimmed if trimmed.endswith("/api") else f"{trimmed}/api"


API_URL: str = normalize_api_url(
    os.environ.get("PAPERCLIP_API_URL")
    or os.environ.get("PAPERCLIP_BASE_URL")
    or "http://localhost:3100"
)
API_KEY: str = os.environ.get("PAPERCLIP_API_KEY", "").strip()
COMPANY: str = os.environ.get("PAPERCLIP_COMPANY_ID", "").strip()
AGENT_ID: str = os.environ.get("PAPERCLIP_AGENT_ID", "").strip()
RUN_ID: str = os.environ.get("PAPERCLIP_RUN_ID", "").strip()

_HTTP_TIMEOUT = 30  # seconds
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# ── Enums (from packages/shared/src/constants.ts, Paperclip v0.3.1) ────────────

ISSUE_STATUSES = ("backlog", "todo", "in_progress", "in_review", "done", "blocked", "cancelled")
ISSUE_OPEN_STATUSES = ("backlog", "todo", "in_progress", "in_review", "blocked")
ISSUE_PRIORITIES = ("critical", "high", "medium", "low")
ISSUE_REVIEW_POLICIES = ("anyone", "not_creator", "human_only")
CHECKOUT_DEFAULT_STATUSES = ("todo", "backlog", "blocked")
APPROVAL_STATUSES = ("pending", "revision_requested", "approved", "rejected", "cancelled")
APPROVAL_TYPES = (
    "hire_agent",
    "approve_ceo_strategy",
    "budget_override_required",
    "request_board_approval",
)
AGENT_STATUSES = ("active", "paused", "idle", "running", "error", "pending_approval", "terminated")
AGENT_ROLES = (
    "ceo",
    "cto",
    "cmo",
    "cfo",
    "security",
    "engineer",
    "designer",
    "pm",
    "qa",
    "devops",
    "researcher",
    "general",
)
GOAL_LEVELS = ("company", "team", "agent", "task")
GOAL_STATUSES = ("planned", "active", "achieved", "cancelled")
PROJECT_STATUSES = ("backlog", "planned", "in_progress", "completed", "cancelled")
ROUTINE_STATUSES = ("active", "paused", "archived")
ROUTINE_CONCURRENCY_POLICIES = ("coalesce_if_active", "always_enqueue", "skip_if_active")
ROUTINE_CATCH_UP_POLICIES = ("skip_missed", "enqueue_missed_with_cap")
ROUTINE_TRIGGER_KINDS = ("schedule", "webhook", "api")
ROUTINE_TRIGGER_SIGNING_MODES = ("bearer", "hmac_sha256", "github_hmac", "none")
INTERACTION_KINDS = (
    "suggest_tasks",
    "ask_user_questions",
    "request_confirmation",
    "request_checkbox_confirmation",
    "request_item_verdicts",
)
INTERACTION_RESOLVER_POLICIES = ("anyone", "not_creator", "human_only")
INTERACTION_CONTINUATION_POLICIES = ("none", "wake_assignee", "wake_assignee_on_accept")
WAKE_SOURCES = ("timer", "assignment", "on_demand", "automation")
WAKE_TRIGGER_DETAILS = ("manual", "ping", "callback", "system")
COST_GROUP_BYS = ("agent", "project", "provider", "agent_model", "biller")
DECISION_STATUSES = ("open", "decided", "expired", "cancelled")
ATTENTION_SORTS = ("activity", "decide")
PIPELINE_REVIEW_DECISIONS = ("approve", "reject", "request_changes")

# ── Errors ─────────────────────────────────────────────────────────────────────

_HINTS: tuple[tuple[str, str], ...] = (
    (
        "Board access required",
        "This endpoint is board-only. Configure PAPERCLIP_API_KEY with a board API key "
        "(pcp_board_..., see create_board_api_key) instead of an agent API key.",
    ),
    (
        "Board authentication required",
        "This endpoint needs a board credential (board API key or local_trusted mode).",
    ),
    (
        "Agent run id required",
        "With an agent API key this action needs a real heartbeat run id "
        "(PAPERCLIP_RUN_ID). Use a board API key instead, or run inside a heartbeat.",
    ),
    (
        "Agent authentication required",
        "This endpoint only works with an agent API key; the configured key is a board key.",
    ),
)


def _hint_for(error_text: str) -> str:
    for needle, hint in _HINTS:
        if needle.lower() in error_text.lower():
            return hint
    return ""


class PaperclipError(ToolError):
    """Raised for any failed Paperclip request. FastMCP reports it as isError=true."""

    def __init__(
        self,
        method: str,
        path: str,
        status: int | None,
        error: str,
        code: str | None = None,
        details: Any = None,
        remediation: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.method, self.path, self.status = method, path, status
        self.error, self.code, self.details, self.remediation = error, code, details, remediation
        self.extra = extra or {}
        parts = [f"{method} {path} failed"]
        parts.append(f"with HTTP {status}: {error}" if status is not None else f": {error}")
        if code:
            parts.append(f"[code={code}]")
        if status == 409:
            parts.append("(409 Conflict: state changed under you; do not blindly retry)")
        if remediation:
            parts.append(f"Remediation: {remediation}")
        hint = _hint_for(error)
        if hint:
            parts.append(f"Hint: {hint}")
        if details:
            parts.append(f"Details: {details}")
        if self.extra:
            parts.append(f"Extra: {self.extra}")
        super().__init__(" ".join(parts))


def fail(message: str) -> PaperclipError:
    """Client-side validation failure (never hits the network)."""
    return PaperclipError("client", "validation", None, message)


def check_enum(value: str, allowed: Iterable[str], field: str) -> str:
    allowed_t = tuple(allowed)
    if value not in allowed_t:
        raise fail(f"Invalid {field} '{value}'. Allowed: {', '.join(allowed_t)}.")
    return value


def check_enum_list(values: Iterable[str], allowed: Iterable[str], field: str) -> list[str]:
    out = [check_enum(v, allowed, field) for v in values]
    if not out:
        raise fail(f"{field} must contain at least one value.")
    return out


def is_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value.strip()))


def clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(value, hi))


# ── HTTP client ────────────────────────────────────────────────────────────────


def build_headers(method: str, has_body: bool) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    if has_body:
        headers["Content-Type"] = "application/json"
    if RUN_ID and method.upper() not in ("GET", "HEAD"):
        headers["X-Paperclip-Run-Id"] = RUN_ID
    return headers


def _parse_body(response: httpx.Response) -> Any:
    if response.status_code == 204 or not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return response.text


_transport: httpx.AsyncBaseTransport | None = None  # tests inject a MockTransport here


async def request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    body: Any = None,
) -> Any:
    """Perform a JSON request against Paperclip. Raises PaperclipError on any failure."""
    if not path.startswith("/"):
        raise fail(f"API path must start with '/': {path}")
    method = method.upper()
    url = f"{API_URL}{path}"
    clean_params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, transport=_transport) as client:
            response = await client.request(
                method,
                url,
                headers=build_headers(method, body is not None),
                params=clean_params or None,
                json=body,
            )
    except httpx.RequestError as exc:
        raise PaperclipError(
            method,
            path,
            None,
            f"Could not reach Paperclip at {API_URL}. Is the server running? ({exc})",
        ) from exc

    parsed = _parse_body(response)
    if response.is_success:
        return {"ok": True} if parsed is None else parsed

    error, code, details, remediation = f"HTTP {response.status_code}", None, None, None
    extra: dict[str, Any] = {}
    if isinstance(parsed, dict):
        error = str(parsed.get("error") or error)
        code = parsed.get("code")
        details = parsed.get("details")
        remediation = parsed.get("remediation")
        known = {"error", "code", "details", "remediation"}
        extra = {k: v for k, v in parsed.items() if k not in known}
    elif isinstance(parsed, str) and parsed.strip():
        error = parsed.strip()[:400]
    raise PaperclipError(
        method, path, response.status_code, error, code, details, remediation, extra
    )


async def get(path: str, params: dict[str, Any] | None = None) -> Any:
    return await request("GET", path, params=params)


async def post(path: str, body: Any = None, params: dict[str, Any] | None = None) -> Any:
    return await request("POST", path, body=body, params=params)


async def put(path: str, body: Any) -> Any:
    return await request("PUT", path, body=body)


async def patch(path: str, body: Any) -> Any:
    return await request("PATCH", path, body=body)


async def delete(path: str) -> Any:
    return await request("DELETE", path)


def company_path(suffix: str) -> str:
    return f"/companies/{COMPANY}{suffix}"


async def resolve_agent_id(agent_id: str = "") -> str:
    """Pick the agent id for checkout: explicit > PAPERCLIP_AGENT_ID > GET /agents/me."""
    if agent_id.strip():
        return agent_id.strip()
    if AGENT_ID:
        return AGENT_ID
    try:
        me = await get("/agents/me")
    except PaperclipError as exc:
        raise fail(
            "agent_id is required: the configured key is not an agent key and "
            f"PAPERCLIP_AGENT_ID is not set ({exc.error})."
        ) from exc
    if isinstance(me, dict) and me.get("id"):
        return str(me["id"])
    raise fail("Could not resolve the current agent id from GET /agents/me.")


# ── Startup ────────────────────────────────────────────────────────────────────


def validate_config() -> None:
    if not COMPANY:
        log.error("Missing required environment variable: PAPERCLIP_COMPANY_ID")
        log.error(
            "Copy .env.example to .env and fill in the values, then run `paperclip-mcp`, "
            "or export the variables in your shell."
        )
        sys.exit(1)
    if not API_KEY:
        log.warning(
            "PAPERCLIP_API_KEY is empty: requests are sent without a bearer token. "
            "This only works against a local_trusted Paperclip deployment."
        )
    if RUN_ID and not is_uuid(RUN_ID):
        log.error(
            "PAPERCLIP_RUN_ID must be a heartbeat run UUID (got %r). "
            "A non-UUID value makes every write request fail server-side.",
            RUN_ID,
        )
        sys.exit(1)


async def probe() -> None:
    """Best-effort connectivity + credential classification; never fatal."""
    try:
        health = await get("/health")
        if isinstance(health, dict):
            log.info(
                "Paperclip reachable: version=%s deploymentMode=%s",
                health.get("version") or health.get("serverVersion"),
                health.get("deploymentMode"),
            )
    except PaperclipError as exc:
        log.warning("Health probe failed: %s", exc.error)
        return
    try:
        me = await get("/cli-auth/me")
        user_id = me.get("userId") if isinstance(me, dict) else "?"
        log.info("Credential: BOARD (user=%s)", user_id)
        return
    except PaperclipError:
        pass
    try:
        me = await get("/agents/me")
        if isinstance(me, dict):
            log.info(
                "Credential: AGENT (%s, id=%s). Board-only tools (approve/reject, pause, "
                "budgets, attention feed, decisions) will return 403.",
                me.get("name"),
                me.get("id"),
            )
    except PaperclipError as exc:
        log.warning("Could not classify credential: %s", exc.error)


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[None]:
    validate_config()
    log.info("paperclip-mcp started: api=%s company=%s", API_URL, COMPANY)
    await probe()
    yield
    log.info("paperclip-mcp stopped.")


# ── MCP server instance ────────────────────────────────────────────────────────

mcp = FastMCP(
    name="paperclip",
    instructions=(
        "Operator console for a Paperclip AI-agent company. Tools map 1:1 to the Paperclip "
        "REST API (v0.3.x). Issue ids accept a UUID or a human identifier such as 'PAP-42'. "
        "All company-scoped tools target the company in PAPERCLIP_COMPANY_ID. Call `whoami` "
        "first to learn whether the credential is a board key (full operator access) or an "
        "agent key (cannot approve/reject, pause agents, or read the attention feed). "
        "Errors are returned as tool errors with the server's message, code and a hint."
    ),
    lifespan=lifespan,
)
