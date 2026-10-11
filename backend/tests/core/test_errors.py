from collections.abc import AsyncIterator

import pytest
from fastapi import APIRouter, HTTPException
from httpx import AsyncClient
from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import Conflict, NotFound
from app.main import create_app
from tests.conftest import open_client


class Item(BaseModel):
    name: str
    count: int


routes = APIRouter(prefix="/api/_t")


@routes.get("/not-found")
async def raise_not_found() -> None:
    raise NotFound(details={"id": "x"})


@routes.get("/conflict")
async def raise_conflict() -> None:
    raise Conflict("Уже есть", code="tutor_already_exists")


@routes.get("/teapot")
async def teapot() -> None:
    raise HTTPException(status_code=418, detail="Я чайник")


@routes.post("/items")
async def create_item(item: Item) -> Item:
    return item


@pytest.fixture
async def tclient(settings: Settings) -> AsyncIterator[AsyncClient]:
    app = create_app(settings)
    app.include_router(routes)
    async with open_client(app) as c:
        yield c


async def test_app_error_rendered(tclient: AsyncClient) -> None:
    r = await tclient.get("/api/_t/not-found")
    assert r.status_code == 404
    assert r.json() == {
        "error": {"code": "not_found", "message": "Не найдено", "details": {"id": "x"}}
    }


async def test_app_error_custom_code_and_cyrillic_message(tclient: AsyncClient) -> None:
    r = await tclient.get("/api/_t/conflict")
    assert r.status_code == 409
    assert r.json()["error"] == {
        "code": "tutor_already_exists",
        "message": "Уже есть",
        "details": {},
    }


async def test_request_validation_error(tclient: AsyncClient) -> None:
    r = await tclient.post("/api/_t/items", json={"name": "a", "count": "много"})
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "validation_error"
    assert body["details"]["fields"][0]["loc"] == ["body", "count"]
    assert set(body["details"]["fields"][0]) == {"loc", "message", "type"}


async def test_unknown_route_uses_error_format(tclient: AsyncClient) -> None:
    r = await tclient.get("/api/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    assert r.json()["error"]["message"] == "Не найдено"


async def test_wrong_method_uses_error_format(tclient: AsyncClient) -> None:
    r = await tclient.delete("/api/health")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "method_not_allowed"
    assert r.json()["error"]["message"] == "Метод не поддерживается"
    assert "GET" in r.headers["allow"]


async def test_custom_http_exception_detail_is_kept(tclient: AsyncClient) -> None:
    r = await tclient.get("/api/_t/teapot")
    assert r.status_code == 418
    assert r.json()["error"] == {"code": "http_error", "message": "Я чайник", "details": {}}
