"""Unit of work `get_db_session` на настоящей зависимости (в остальных тестах она подменена)."""

from collections.abc import AsyncIterator
from types import TracebackType
from typing import Any

import pytest
from asgi_lifespan import LifespanManager
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from starlette.types import Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.db import DbSession
from app.core.errors import Conflict
from app.main import create_app


class FakeSession:
    def __init__(self, events: list[str], *, fail_commit: bool) -> None:
        self.events = events
        self.fail_commit = fail_commit

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.events.append("close")

    async def commit(self) -> None:
        self.events.append("commit")
        if self.fail_commit:
            raise RuntimeError("commit failed")

    async def rollback(self) -> None:
        self.events.append("rollback")


routes = APIRouter(prefix="/api/_t")


@routes.post("/write")
async def write(session: DbSession) -> dict[str, str]:
    return {"ok": "yes"}


@routes.post("/conflict")
async def conflict(session: DbSession) -> None:
    raise Conflict("Уже есть")


async def _client(
    settings: Settings, events: list[str], *, fail_commit: bool = False
) -> AsyncIterator[AsyncClient]:
    app = create_app(settings)
    app.include_router(routes)

    async def recording(scope: Scope, receive: Receive, send: Send) -> None:
        async def record(message: Message) -> None:
            if message["type"] == "http.response.start":
                events.append("response_start")
            await send(message)

        await app(scope, receive, record)

    transport = ASGITransport(app=recording, raise_app_exceptions=False)
    async with LifespanManager(app), AsyncClient(transport=transport, base_url="http://t") as c:
        app.state.sessionmaker = lambda: FakeSession(events, fail_commit=fail_commit)
        yield c


@pytest.fixture
def events() -> list[str]:
    return []


async def test_commit_happens_before_response(settings: Settings, events: list[str]) -> None:
    async for c in _client(settings, events):
        r = await c.post("/api/_t/write")
    assert r.status_code == 200
    assert events.index("commit") < events.index("response_start")


async def test_failed_commit_returns_500(settings: Settings, events: list[str]) -> None:
    async for c in _client(settings, events, fail_commit=True):
        r = await c.post("/api/_t/write")
    assert r.status_code == 500
    body: dict[str, Any] = r.json()
    assert body["error"]["code"] == "internal_error"


async def test_app_error_rolls_back(settings: Settings, events: list[str]) -> None:
    async for c in _client(settings, events):
        r = await c.post("/api/_t/conflict")
    assert r.status_code == 409
    assert "rollback" in events
    assert "commit" not in events
