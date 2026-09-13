"""Test fixtures: env config is fixed before paperclip_mcp is imported, HTTP is mocked."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
import pytest_asyncio

os.environ.setdefault("PAPERCLIP_API_URL", "http://paperclip.test:3100")
os.environ.setdefault("PAPERCLIP_API_KEY", "pcp_board_testkey")
os.environ.setdefault("PAPERCLIP_COMPANY_ID", "11111111-1111-1111-1111-111111111111")
os.environ.setdefault("PAPERCLIP_AGENT_ID", "22222222-2222-2222-2222-222222222222")
os.environ.pop("PAPERCLIP_RUN_ID", None)

from fastmcp import Client  # noqa: E402

from paperclip_mcp import core  # noqa: E402
from paperclip_mcp.server import mcp  # noqa: E402

COMPANY = os.environ["PAPERCLIP_COMPANY_ID"]
AGENT = os.environ["PAPERCLIP_AGENT_ID"]

Responder = Callable[[httpx.Request], httpx.Response | None]


@dataclass
class Recorder:
    requests: list[httpx.Request] = field(default_factory=list)
    responders: list[Responder] = field(default_factory=list)

    def respond(self, responder: Responder) -> None:
        self.responders.append(responder)

    @property
    def last(self) -> httpx.Request:
        assert self.requests, "no request was recorded"
        return self.requests[-1]

    def body(self, index: int = -1) -> Any:
        raw = self.requests[index].content
        return json.loads(raw) if raw else None


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    rec = Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        rec.requests.append(request)
        for responder in rec.responders:
            response = responder(request)
            if response is not None:
                return response
        return httpx.Response(200, json={"ok": True, "path": request.url.path})

    monkeypatch.setattr(core, "_transport", httpx.MockTransport(handler))
    return rec


@pytest_asyncio.fixture
async def client(recorder: Recorder) -> AsyncIterator[Client]:
    async with Client(mcp) as c:
        recorder.requests.clear()  # drop the startup probe calls
        yield c


async def call(_client: Client, _tool: str, **args: Any) -> Any:
    result = await _client.call_tool(_tool, args, raise_on_error=True)
    return result.data if result.data is not None else result.content


async def call_error(_client: Client, _tool: str, **args: Any) -> str:
    result = await _client.call_tool(_tool, args, raise_on_error=False)
    assert result.is_error, f"expected {_tool} to fail"
    return result.content[0].text  # type: ignore[union-attr]
