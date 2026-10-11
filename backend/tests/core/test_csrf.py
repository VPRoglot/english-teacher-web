from asgi_lifespan import LifespanManager
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app
from tests.conftest import open_client

routes = APIRouter(prefix="/api/_t")


@routes.post("/echo")
async def echo() -> dict[str, bool]:
    return {"ok": True}


def _app(settings: Settings) -> FastAPI:
    application = create_app(settings)
    application.include_router(routes)
    return application


async def test_post_without_token_is_rejected(settings: Settings) -> None:
    app = _app(settings)
    async with (
        LifespanManager(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as c,
    ):
        r = await c.post("/api/_t/echo")
    assert r.status_code == 403
    error = r.json()["error"]
    assert error["code"] == "csrf_failed"
    assert error["message"] == "Сессия страницы устарела. Обновите страницу и повторите."


async def test_header_must_match_cookie(settings: Settings) -> None:
    app = _app(settings)
    async with open_client(app) as c:
        r = await c.post("/api/_t/echo", headers={"X-CSRF-Token": "x"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"


async def test_non_ascii_header_is_rejected_not_500(settings: Settings) -> None:
    app = _app(settings)
    async with open_client(app) as c:
        r = await c.post("/api/_t/echo", headers=[(b"X-CSRF-Token", "é".encode("latin-1"))])
    assert r.status_code == 403


async def test_cookie_without_header_is_rejected(settings: Settings) -> None:
    app = _app(settings)
    async with open_client(app) as c:
        del c.headers["X-CSRF-Token"]
        r = await c.post("/api/_t/echo")
    assert r.status_code == 403


async def test_empty_cookie_and_header_are_rejected(settings: Settings) -> None:
    app = _app(settings)
    async with (
        LifespanManager(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as c,
    ):
        r = await c.post("/api/_t/echo", headers={"Cookie": "csrf_token=", "X-CSRF-Token": ""})
    assert r.status_code == 403


async def test_post_with_token_passes(settings: Settings) -> None:
    app = _app(settings)
    async with open_client(app) as c:
        r = await c.post("/api/_t/echo")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


async def test_non_api_path_is_not_checked(settings: Settings) -> None:
    app = _app(settings)
    async with (
        LifespanManager(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as c,
    ):
        r = await c.post("/other")
    assert r.status_code == 404  # не 403: вне /api/ CSRF-проверки нет


async def test_get_does_not_need_token(settings: Settings) -> None:
    app = _app(settings)
    async with (
        LifespanManager(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as c,
    ):
        r = await c.get("/api/health")
    assert r.status_code == 200


async def test_csrf_cookie_is_reused(client: AsyncClient) -> None:
    before = client.cookies["csrf_token"]
    r = await client.get("/api/auth/csrf")
    assert r.status_code == 204
    assert client.cookies["csrf_token"] == before
    assert "set-cookie" not in r.headers


async def test_malformed_cookie_is_replaced(settings: Settings) -> None:
    app = _app(settings)
    async with (
        LifespanManager(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as c,
    ):
        r = await c.get("/api/auth/csrf", headers={"Cookie": "csrf_token=short"})
    assert r.status_code == 204
    assert "csrf_token=short" not in r.headers["set-cookie"]


async def test_csrf_cookie_attributes(settings: Settings) -> None:
    app = _app(settings)
    async with (
        LifespanManager(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as c,
    ):
        r = await c.get("/api/auth/csrf")
    set_cookie = r.headers["set-cookie"].lower()
    assert r.status_code == 204
    assert "samesite=lax" in set_cookie
    assert "secure" in set_cookie
    assert "httponly" not in set_cookie
    assert "path=/" in set_cookie
    assert "max-age" not in set_cookie
    assert "expires" not in set_cookie


async def test_csrf_operation_id(settings: Settings) -> None:
    spec = _app(settings).openapi()
    assert spec["paths"]["/api/auth/csrf"]["get"]["operationId"] == "get_csrf"
