import json
import re
from collections.abc import AsyncIterator

import pytest
from asgi_lifespan import LifespanManager
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.core.logging import configure_logging
from app.main import create_app

HEX32 = re.compile(r"[0-9a-f]{32}")

routes = APIRouter(prefix="/api/_t")


@routes.get("/boom")
async def boom() -> None:
    raise RuntimeError("boom")


@pytest.fixture
async def tclient(settings: Settings) -> AsyncIterator[AsyncClient]:
    app = create_app(settings)
    app.include_router(routes)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with LifespanManager(app), AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_generates_request_id(client: AsyncClient) -> None:
    r = await client.get("/api/health")
    assert HEX32.fullmatch(r.headers["X-Request-ID"])


async def test_keeps_valid_incoming_request_id(client: AsyncClient) -> None:
    r = await client.get("/api/health", headers={"X-Request-ID": "abc-123.DEF_4"})
    assert r.headers["X-Request-ID"] == "abc-123.DEF_4"


@pytest.mark.parametrize("bad", ["a b", "x" * 65, "<script>", ""])
async def test_replaces_invalid_incoming_request_id(client: AsyncClient, bad: str) -> None:
    r = await client.get("/api/health", headers={"X-Request-ID": bad})
    assert r.headers["X-Request-ID"] != bad
    assert HEX32.fullmatch(r.headers["X-Request-ID"])


async def test_unhandled_exception_returns_500_with_request_id(tclient: AsyncClient) -> None:
    r = await tclient.get("/api/_t/boom", headers={"X-Request-ID": "req-1"})
    assert r.status_code == 500
    assert r.headers["X-Request-ID"] == "req-1"
    assert r.json() == {
        "error": {
            "code": "internal_error",
            "message": "Внутренняя ошибка сервера",
            "details": {"request_id": "req-1"},
        }
    }


async def test_access_log_contains_request_id(
    client: AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging("INFO", json=True)
    await client.get("/api/health", headers={"X-Request-ID": "log-1"})
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    entry = next(line for line in lines if line.get("event") == "http_request")
    assert entry["request_id"] == "log-1"
    assert entry["status"] == 200
    assert entry["path"] == "/api/health"
    assert entry["method"] == "GET"
    assert isinstance(entry["duration_ms"], float)


async def test_unhandled_exception_is_logged(
    tclient: AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging("INFO", json=True)
    await tclient.get("/api/_t/boom", headers={"X-Request-ID": "req-2"})
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    entry = next(line for line in lines if line.get("event") == "unhandled_error")
    assert entry["request_id"] == "req-2"
    assert "RuntimeError: boom" in entry["exception"]
