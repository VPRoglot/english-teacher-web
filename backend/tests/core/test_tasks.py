import asyncio
from itertools import pairwise
from typing import Annotated, Any

import pytest
import structlog
from sqlalchemy import text
from taskiq import (
    BrokerMessage,
    Context,
    InMemoryBroker,
    TaskiqDepends,
    TaskiqMiddleware,
)
from taskiq.middlewares import SmartRetryMiddleware
from taskiq_redis import RedisStreamBroker

from app.core.config import Settings
from app.core.request_id import _request_id, get_request_id
from app.core.tasks import (
    BrokerTaskQueue,
    DelayedRetryMiddleware,
    RequestIdTaskMiddleware,
    create_broker,
    task_middlewares,
)
from app.tasks import setup_worker
from tests.conftest import make_settings


async def test_enqueue_kicks_task_by_name_with_request_id_label() -> None:
    broker = InMemoryBroker()
    seen: dict[str, Any] = {}

    async def probe(x: int, context: Annotated[Context, TaskiqDepends()]) -> None:
        seen["x"] = x
        seen["labels"] = context.message.labels

    broker.register_task(probe, task_name="test.probe")
    await broker.startup()
    token = _request_id.set("rid-1")
    try:
        await BrokerTaskQueue(broker, timeout_seconds=5).enqueue("test.probe", x=1)
        await broker.wait_all()
    finally:
        _request_id.reset(token)
        await broker.shutdown()
    assert seen == {"x": 1, "labels": {"request_id": "rid-1"}}


async def test_enqueue_without_request_id_sends_no_label() -> None:
    broker = InMemoryBroker()
    seen: dict[str, Any] = {}

    async def probe(context: Annotated[Context, TaskiqDepends()]) -> None:
        seen["labels"] = context.message.labels

    broker.register_task(probe, task_name="test.probe")
    await broker.startup()
    try:
        await BrokerTaskQueue(broker, timeout_seconds=5).enqueue("test.probe")
        await broker.wait_all()
    finally:
        await broker.shutdown()
    assert seen == {"labels": {}}


async def test_middleware_binds_request_id_and_task_name_while_task_runs() -> None:
    broker = InMemoryBroker().with_middlewares(RequestIdTaskMiddleware())
    seen: dict[str, Any] = {}

    async def probe() -> None:
        seen["request_id"] = get_request_id()
        seen["log_context"] = structlog.contextvars.get_contextvars()

    broker.register_task(probe, task_name="test.probe")
    await broker.startup()
    try:
        token = _request_id.set("rid-2")
        try:
            await BrokerTaskQueue(broker, timeout_seconds=5).enqueue("test.probe")
        finally:
            _request_id.reset(token)
        await broker.wait_all()
    finally:
        await broker.shutdown()
    assert seen["request_id"] == "rid-2"
    assert seen["log_context"] == {"request_id": "rid-2", "task_name": "test.probe"}
    assert structlog.contextvars.get_contextvars() == {}


async def _run_failing_task(*middlewares: TaskiqMiddleware) -> int:
    broker = InMemoryBroker(propagate_exceptions=False).with_middlewares(*middlewares)
    attempts = 0

    async def always_fails() -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("boom")

    broker.register_task(always_fails, task_name="test.fails", retry_on_error=True)
    await broker.startup()
    try:
        await BrokerTaskQueue(broker, timeout_seconds=5).enqueue("test.fails")
        for _ in range(10):  # каждый повтор — новая задача, wait_all ждёт только запущенные
            await broker.wait_all()
    finally:
        await broker.shutdown()
    return attempts


async def test_retries_wait_with_growing_delay(retry_sleeps: list[float]) -> None:
    attempts = await _run_failing_task(*task_middlewares())
    assert attempts == 5
    assert len(retry_sleeps) == 4  # пауза перед каждым из 4 повторов
    assert retry_sleeps == sorted(retry_sleeps)
    assert 5 <= retry_sleeps[0] < 6  # default_delay + джиттер < 1 с
    assert all(a < b for a, b in pairwise(retry_sleeps))
    assert retry_sleeps[-1] == 60  # дошло до потолка (метка delay растёт с каждым повтором)


async def test_retry_delay_is_capped(retry_sleeps: list[float]) -> None:
    middleware = DelayedRetryMiddleware(
        default_retry_count=6,
        default_retry_label=True,
        default_delay=5,
        use_jitter=True,
        use_delay_exponent=True,
        max_delay_exponent=12,
    )
    await _run_failing_task(middleware)
    assert len(retry_sleeps) == 5
    assert max(retry_sleeps) <= 12  # потолок действует и вместе с джиттером
    assert retry_sleeps[-1] == 12


def test_broker_retries_five_times(settings: Settings) -> None:
    broker = create_broker(settings)
    retry = [m for m in broker.middlewares if isinstance(m, SmartRetryMiddleware)]
    assert len(retry) == 1 and retry[0].default_retry_count == 5


async def test_enqueue_times_out_when_broker_hangs() -> None:
    class HangingBroker(InMemoryBroker):
        async def kick(self, message: BrokerMessage) -> None:
            await asyncio.sleep(3600)

    queue = BrokerTaskQueue(HangingBroker(), timeout_seconds=0.05)
    with pytest.raises(TimeoutError):
        await queue.enqueue("test.probe")


def test_broker_caps_stream_length_and_reads_group_from_start(settings: Settings) -> None:
    broker = create_broker(settings)
    assert isinstance(broker, RedisStreamBroker)
    assert broker.maxlen == 10_000
    assert broker.approximate is True
    assert broker.consumer_id == "0"  # id, с которого создаётся consumer group


def test_broker_connection_timeouts_exceed_xread_block(settings: Settings) -> None:
    broker = create_broker(settings)
    assert isinstance(broker, RedisStreamBroker)
    kwargs = broker.connection_pool.connection_kwargs
    assert kwargs["socket_timeout"] == 5
    assert kwargs["socket_connect_timeout"] == 5
    assert kwargs["socket_timeout"] > broker.block / 1000  # xread блокируется на 2 с


async def test_worker_state_has_sessionmaker(settings: Settings) -> None:
    broker = setup_worker(InMemoryBroker(), settings)
    await broker.startup()
    try:
        async with broker.state.sessionmaker() as session:
            assert (await session.execute(text("select 1"))).scalar_one() == 1
    finally:
        await broker.shutdown()


async def test_worker_startup_does_not_connect_to_db() -> None:
    unreachable = make_settings(database_url="postgresql+asyncpg://u:p@127.0.0.1:1/x")
    broker = setup_worker(InMemoryBroker(), unreachable)
    await broker.startup()  # движок ленивый: без БД worker всё равно стартует
    await broker.shutdown()
