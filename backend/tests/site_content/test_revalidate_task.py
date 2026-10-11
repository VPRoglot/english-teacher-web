from collections.abc import Callable

import httpx
import pytest
from taskiq import InMemoryBroker

from app.core.config import Settings
from app.core.request_id import _request_id
from app.core.tasks import BrokerTaskQueue, task_middlewares
from app.site_content.tasks import REVALIDATE_SITE_TASK, HttpRevalidator, RevalidateFailed
from app.tasks import setup_worker

SECRET = "s3cret-s3cret-123"
URL = "http://web.test/api/revalidate"


def _mock(
    requests: list[httpx.Request], respond: Callable[[httpx.Request], httpx.Response]
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return respond(request)

    return httpx.MockTransport(handler)


async def _revalidate(transport: httpx.MockTransport) -> None:
    async with httpx.AsyncClient(transport=transport) as client:
        await HttpRevalidator(client, URL, SECRET).revalidate()


async def test_http_revalidator_posts_with_bearer_secret() -> None:
    requests: list[httpx.Request] = []
    await _revalidate(_mock(requests, lambda r: httpx.Response(204)))
    assert [(r.method, str(r.url)) for r in requests] == [("POST", URL)]
    assert requests[0].headers["Authorization"] == f"Bearer {SECRET}"
    assert "X-Request-ID" not in requests[0].headers


async def test_http_revalidator_forwards_request_id() -> None:
    requests: list[httpx.Request] = []
    token = _request_id.set("rid-3")
    try:
        await _revalidate(_mock(requests, lambda r: httpx.Response(204)))
    finally:
        _request_id.reset(token)
    assert requests[0].headers["X-Request-ID"] == "rid-3"


@pytest.mark.parametrize("status", [401, 500, 503])
async def test_http_revalidator_raises_on_error_status(status: int) -> None:
    requests: list[httpx.Request] = []
    with pytest.raises(RevalidateFailed) as exc_info:
        await _revalidate(_mock(requests, lambda r: httpx.Response(status)))
    assert str(status) in str(exc_info.value)
    assert SECRET not in str(exc_info.value)


async def test_http_revalidator_raises_on_network_error() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(RevalidateFailed):
        await _revalidate(_mock([], refuse))


async def test_worker_runs_revalidate_task(settings: Settings) -> None:
    requests: list[httpx.Request] = []
    transport = _mock(requests, lambda r: httpx.Response(204))
    broker = InMemoryBroker()
    setup_worker(broker, settings, transport=transport)
    await broker.startup()
    try:
        await BrokerTaskQueue(broker, timeout_seconds=5).enqueue(REVALIDATE_SITE_TASK)
        await broker.wait_all()
    finally:
        await broker.shutdown()
    assert [(r.method, str(r.url)) for r in requests] == [("POST", settings.revalidate_url)]
    assert requests[0].headers["Authorization"] == "Bearer test-revalidate-secret"


async def _run_with_retries(settings: Settings, transport: httpx.MockTransport) -> None:
    broker = InMemoryBroker(propagate_exceptions=False)
    broker.with_middlewares(*task_middlewares())
    setup_worker(broker, settings, transport=transport)
    await broker.startup()
    try:
        await BrokerTaskQueue(broker, timeout_seconds=5).enqueue(REVALIDATE_SITE_TASK)
        for _ in range(10):  # каждый повтор — новая задача, wait_all ждёт только уже запущенные
            await broker.wait_all()
    finally:
        await broker.shutdown()


async def test_task_is_retried_until_next_accepts(
    settings: Settings, retry_sleeps: list[float]
) -> None:
    requests: list[httpx.Request] = []
    transport = _mock(
        requests, lambda r: httpx.Response(503 if len(requests) < 3 else 204)
    )  # Next перезапускается: первые два ответа — 503
    await _run_with_retries(settings, transport)
    assert len(requests) == 3
    assert len(retry_sleeps) == 2


async def test_task_gives_up_after_five_attempts(
    settings: Settings, retry_sleeps: list[float]
) -> None:
    requests: list[httpx.Request] = []
    await _run_with_retries(settings, _mock(requests, lambda r: httpx.Response(500)))
    assert len(requests) == 5
    assert len(retry_sleeps) == 4
