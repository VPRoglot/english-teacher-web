import asyncio
from asyncio import sleep
from typing import Annotated, Any, Protocol

import structlog
from fastapi import Depends, Request
from taskiq import AsyncBroker, TaskiqMessage, TaskiqMiddleware, TaskiqResult
from taskiq.kicker import AsyncKicker
from taskiq.middlewares import SmartRetryMiddleware
from taskiq_redis import RedisStreamBroker

from app.core.config import Settings
from app.core.request_id import _request_id, get_request_id

log = structlog.get_logger("app.tasks")

_STREAM_MAXLEN = 10_000
_REDIS_SOCKET_TIMEOUT = 5  # секунд


class TaskQueue(Protocol):
    async def enqueue(self, task_name: str, /, **kwargs: Any) -> None: ...


class BrokerTaskQueue(TaskQueue):
    """Ставит задачи по имени: API не импортирует модули задач."""

    def __init__(self, broker: AsyncBroker, *, timeout_seconds: float) -> None:
        self._broker = broker
        self._timeout_seconds = timeout_seconds

    async def enqueue(self, task_name: str, /, **kwargs: Any) -> None:
        """Ставит задачу; при зависшем брокере через `timeout_seconds` бросает `TimeoutError`."""
        labels: dict[str, Any] = {}
        request_id = get_request_id()
        if request_id:
            labels["request_id"] = request_id
        async with asyncio.timeout(self._timeout_seconds):
            await AsyncKicker(task_name=task_name, broker=self._broker, labels=labels).kiq(**kwargs)


class RequestIdTaskMiddleware(TaskiqMiddleware):
    """Переносит request id из метки задачи в логи и в `get_request_id()` на время выполнения."""

    def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        request_id = message.labels.get("request_id")
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(task_name=message.task_name)
        if isinstance(request_id, str):
            structlog.contextvars.bind_contextvars(request_id=request_id)
            _request_id.set(request_id)
        log.info("task_started")
        return message

    def post_execute(self, message: TaskiqMessage, result: TaskiqResult[Any]) -> None:
        log.info("task_finished", is_err=result.is_err)
        structlog.contextvars.clear_contextvars()
        _request_id.set(None)


class DelayedRetryMiddleware(SmartRetryMiddleware):
    """Повтор с настоящей паузой.

    Без schedule_source SmartRetryMiddleware только кладёт метку `delay`, а Redis-брокер
    её не учитывает: повторы шли бы подряд. Планировщик (отдельный процесс) не нужен —
    выдерживаем паузу прямо в worker перед повторной постановкой. Занимает один слот
    выполнения на время паузы, не дольше `max_delay_exponent`.
    """

    async def on_send(
        self, kicker: AsyncKicker[Any, Any], message: TaskiqMessage, delay: float
    ) -> None:
        await sleep(min(delay, self.max_delay_exponent))
        await super().on_send(kicker, message, delay)


def task_middlewares() -> list[TaskiqMiddleware]:
    return [
        # Метки retry_on_error/max_retries задачи в сообщение попадают только при вызове
        # через зарегистрированную задачу, а API ставит задачи по имени, поэтому
        # повтор по умолчанию включён для всех задач.
        # Каждая задача повторяется при ошибке → задачи обязаны быть идемпотентными.
        DelayedRetryMiddleware(
            default_retry_count=5,
            default_retry_label=True,
            default_delay=5,
            use_jitter=True,
            use_delay_exponent=True,
            max_delay_exponent=60,
        ),
        RequestIdTaskMiddleware(),
    ]


def create_broker(settings: Settings) -> AsyncBroker:
    # Пул соединений ленивый: брокер создаётся и без доступного Redis.
    return RedisStreamBroker(
        url=settings.redis_url,
        # Поток не растёт бесконечно; approximate — обрезка пачками, дешевле для Redis.
        maxlen=_STREAM_MAXLEN,
        approximate=True,
        # Consumer group создаётся с начала потока: задачи, поставленные до первого
        # старта worker (API стартует раньше), не теряются. Значение по умолчанию "$"
        # пропустило бы их.
        consumer_id="0",
        # xreadgroup блокируется на xread_block (2 с), поэтому socket_timeout должен быть
        # заметно больше, иначе простаивающее соединение рвётся по таймауту сокета.
        socket_timeout=_REDIS_SOCKET_TIMEOUT,
        socket_connect_timeout=_REDIS_SOCKET_TIMEOUT,
    ).with_middlewares(*task_middlewares())


def get_task_queue(request: Request) -> TaskQueue:
    queue: TaskQueue = request.app.state.task_queue
    return queue


TaskQueueDep = Annotated[TaskQueue, Depends(get_task_queue)]
