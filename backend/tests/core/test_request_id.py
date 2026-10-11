import json
import re
from collections.abc import AsyncIterator

import pytest
from fastapi import APIRouter
from httpx import AsyncClient

from app.core.config import Settings
from app.core.logging import configure_logging
from app.main import create_app
from tests.conftest import open_client

HEX32 = re.compile(r"[0-9a-f]{32}")

routes = APIRouter(prefix="/api/_t")


@routes.get("/ok")
async def ok() -> dict[str, str]:
    return {"status": "ok"}


@routes.get("/boom")
async def boom() -> None:
    raise RuntimeError("boom")


@pytest.fixture
async def tclient(settings: Settings) -> AsyncIterator[AsyncClient]:
    app = create_app(settings)
    app.include_router(routes)
    async with open_client(app, raise_app_exceptions=False) as c:
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
    tclient: AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging("INFO", json=True)
    await tclient.get("/api/_t/ok", headers={"X-Request-ID": "log-1"})
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    entry = next(line for line in lines if line.get("event") == "http_request")
    assert entry["request_id"] == "log-1"
    assert entry["status"] == 200
    assert entry["path"] == "/api/_t/ok"
    assert entry["method"] == "GET"
    assert isinstance(entry["duration_ms"], float)


@pytest.mark.parametrize("path", ["/api/health", "/api/health/ready"])
async def test_health_access_log_is_debug(
    client: AsyncClient, capsys: pytest.CaptureFixture[str], path: str
) -> None:
    configure_logging("INFO", json=True)
    await client.get(path)
    assert "http_request" not in capsys.readouterr().out


async def test_unhandled_exception_is_logged(
    tclient: AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging("INFO", json=True)
    await tclient.get("/api/_t/boom", headers={"X-Request-ID": "req-2"})
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    entry = next(line for line in lines if line.get("event") == "unhandled_error")
    assert entry["request_id"] == "req-2"
    assert "RuntimeError: boom" in entry["exception"]


@pytest.mark.parametrize(
    ("path", "logged"),
    [
        ("/api/auth/invitations/SECRET-token_1", "/api/auth/invitations/***"),
        ("/api/auth/invitations/SECRET-token_1/accept", "/api/auth/invitations/***/accept"),
        ("/api/auth/password-resets/SECRET-token_1", "/api/auth/password-resets/***"),
    ],
)
async def test_access_log_hides_one_time_tokens(
    client: AsyncClient, capsys: pytest.CaptureFixture[str], path: str, logged: str
) -> None:
    configure_logging("INFO", json=True)
    await client.get(path)
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    # httpx пишет собственный лог клиента с полным URL — проверяется только лог приложения.
    entry = next(line for line in lines if line.get("event") == "http_request")
    assert entry["path"] == logged
    assert "SECRET" not in json.dumps(entry)
