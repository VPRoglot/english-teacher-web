from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Protocol

import pytest
from fastapi import FastAPI, Request
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import get_db_session
from app.core.tasks import get_task_queue
from app.leads.captcha import get_captcha_verifier
from app.main import create_app
from tests.conftest import FakeTaskQueue, open_client
from tests.factories import TEST_PASSWORD, make_family, make_parent
from tests.leads.conftest import FakeCaptcha, valid_lead

LEADS_URL = "/api/public/leads"


class ClientFactory(Protocol):
    def __call__(
        self, forwarded_allow_ips: str, *, extra: Callable[[FastAPI], None] | None = None
    ) -> AbstractAsyncContextManager[AsyncClient]: ...


def _xff(ip: str) -> dict[str, str]:
    return {"X-Forwarded-For": ip}


@pytest.fixture
def proxied_client(
    settings: Settings, db_session: AsyncSession, redis: Redis, task_queue: FakeTaskQueue
) -> ClientFactory:
    """Фабрика клиентов к приложению с заданным `forwarded_allow_ips`."""

    @asynccontextmanager
    async def factory(
        forwarded_allow_ips: str, *, extra: Callable[[FastAPI], None] | None = None
    ) -> AsyncIterator[AsyncClient]:
        await redis.flushdb()
        application = create_app(
            settings.model_copy(update={"forwarded_allow_ips": forwarded_allow_ips})
        )

        async def _session() -> AsyncIterator[AsyncSession]:
            yield db_session

        application.dependency_overrides[get_db_session] = _session
        application.dependency_overrides[get_task_queue] = lambda: task_queue
        application.dependency_overrides[get_captcha_verifier] = lambda: FakeCaptcha(True)
        if extra is not None:
            extra(application)
        async with open_client(application) as c:
            yield c

    return factory


async def _post_lead(client: AsyncClient, ip: str) -> int:
    r = await client.post(LEADS_URL, json=valid_lead(), headers=_xff(ip))
    return r.status_code


async def test_lead_rate_limit_uses_forwarded_ip(proxied_client: ClientFactory) -> None:
    async with proxied_client("*") as c:
        for _ in range(3):
            assert await _post_lead(c, "203.0.113.7") == 201
        assert await _post_lead(c, "203.0.113.7") == 429
        assert await _post_lead(c, "203.0.113.8") == 201


async def test_forwarded_headers_ignored_without_trust(proxied_client: ClientFactory) -> None:
    async with proxied_client("") as c:
        for i in range(3):
            assert await _post_lead(c, f"203.0.113.{i + 1}") == 201
        assert await _post_lead(c, "203.0.113.99") == 429


async def _login(client: AsyncClient, ip: str) -> int:
    r = await client.post(
        "/api/auth/login",
        json={"login": "parent@example.com", "password": "wrong-" + TEST_PASSWORD},
        headers=_xff(ip),
    )
    return r.status_code


async def test_login_rate_limit_uses_forwarded_ip(
    proxied_client: ClientFactory, db_session: AsyncSession
) -> None:
    await make_parent(db_session, await make_family(db_session))
    async with proxied_client("*") as c:
        for _ in range(5):
            assert await _login(c, "203.0.113.7") == 401
        assert await _login(c, "203.0.113.7") == 429
        # Тот же логин с другого клиентского IP считается отдельной парой.
        assert await _login(c, "203.0.113.8") == 401


async def test_forwarded_proto_sets_https_scheme(proxied_client: ClientFactory) -> None:
    def add_route(application: FastAPI) -> None:
        @application.get("/api/_scheme")
        async def scheme(request: Request) -> dict[str, str]:
            return {"scheme": request.url.scheme}

    async with proxied_client("*", extra=add_route) as c:
        r = await c.get("/api/_scheme", headers={"X-Forwarded-Proto": "http"})
        assert r.json() == {"scheme": "http"}
        r = await c.get("/api/_scheme", headers={"X-Forwarded-Proto": "https"})
        assert r.json() == {"scheme": "https"}
