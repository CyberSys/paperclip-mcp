"""Identity, health, company, board API keys, secrets catalog and the raw API escape hatch."""

from __future__ import annotations

from typing import Any

from paperclip_mcp.core import (
    COMPANY,
    PaperclipError,
    company_path,
    fail,
    get,
    mcp,
    post,
    request,
)


@mcp.tool(tags={"admin"})
async def whoami() -> Any:
    """Identify the configured credential: board user (memberships, isInstanceAdmin) or agent
    (id, name, role). Call this first to know which tools will be forbidden."""
    try:
        me = await get("/cli-auth/me")
        return {"actorType": "board", **(me if isinstance(me, dict) else {"raw": me})}
    except PaperclipError as board_exc:
        if board_exc.status not in (401, 403, 404):
            raise
    try:
        me = await get("/agents/me")
        return {"actorType": "agent", **(me if isinstance(me, dict) else {"raw": me})}
    except PaperclipError as agent_exc:
        raise fail(
            "Credential is neither a board key nor an agent key, or Paperclip rejected it: "
            f"{agent_exc.error}"
        ) from agent_exc


@mcp.tool(tags={"admin"})
async def get_health() -> Any:
    """Server health, version and deploymentMode (local_trusted needs no token)."""
    return await get("/health")


@mcp.tool(tags={"admin"})
async def get_company() -> Any:
    """The configured company: name, status, issuePrefix ("PAP" in PAP-42), budget and spend."""
    return await get(company_path(""))


@mcp.tool(tags={"admin"})
async def list_companies() -> Any:
    """List companies the board user can access (to find PAPERCLIP_COMPANY_ID). Board key only."""
    return await get("/companies")


@mcp.tool(tags={"admin"})
async def create_board_api_key(name: str = "paperclip-mcp", expires_at: str = "") -> Any:
    """Mint a board API key (pcp_board_..., shown once). Needs a board credential: an existing board
    key, or no token at all on a local_trusted deployment. Use it as PAPERCLIP_API_KEY to unlock the
    operator-only tools.

    Args:
        name: Key label (1-120).
        expires_at: ISO datetime; default 30 days.
    """
    body: dict[str, Any] = {"name": name or "paperclip-mcp", "requestedCompanyId": COMPANY}
    if expires_at:
        body["expiresAt"] = expires_at
    return await post("/board-api-keys", body)


@mcp.tool(tags={"admin"})
async def list_secret_catalog() -> Any:
    """Secrets available to agents as {id, name, key, status}: names only, never values."""
    return await get(company_path("/secrets/catalog"))


@mcp.tool(tags={"admin"})
async def api_request(
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> Any:
    """Escape hatch: call any Paperclip /api endpoint that has no dedicated tool.

    Args:
        method: GET, POST, PUT, PATCH or DELETE.
        path: Path relative to /api, starting with "/" (e.g. "/companies/{id}/org").
              "{company}" is replaced by the configured company id.
        params: Query parameters.
        body: JSON body for write methods.
    """
    method = method.upper()
    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        raise fail("method must be one of GET, POST, PUT, PATCH, DELETE.")
    if not path.startswith("/") or ".." in path:
        raise fail("path must start with '/' and must not contain '..'.")
    return await request(method, path.replace("{company}", COMPANY), params=params, body=body)
