from typing import Annotated, Any

import structlog
from taskiq import Context, InMemoryBroker, TaskiqDepends
from taskiq.middlewares import SmartRetryMiddleware

from app.core.config import Settings
from app.core.request_id import _request_id, get_request_id
from app.core.tasks import BrokerTaskQueue, RequestIdTaskMiddleware, create_broker


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
        await BrokerTaskQueue(broker).enqueue("test.probe", x=1)
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
        await BrokerTaskQueue(broker).enqueue("test.probe")
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
            await BrokerTaskQueue(broker).enqueue("test.probe")
        finally:
            _request_id.reset(token)
        await broker.wait_all()
    finally:
        await broker.shutdown()
    assert seen["request_id"] == "rid-2"
    assert seen["log_context"] == {"request_id": "rid-2", "task_name": "test.probe"}
    assert structlog.contextvars.get_contextvars() == {}


def test_broker_retries_five_times(settings: Settings) -> None:
    broker = create_broker(settings)
    retry = [m for m in broker.middlewares if isinstance(m, SmartRetryMiddleware)]
    assert len(retry) == 1 and retry[0].default_retry_count == 5
