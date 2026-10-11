import httpx
from taskiq import AsyncBroker, TaskiqEvents, TaskiqState

from app.core.config import Settings
from app.core.db import create_db_engine, create_sessionmaker
from app.site_content.tasks import HttpRevalidator, register_tasks


def setup_worker(
    broker: AsyncBroker,
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AsyncBroker:
    """Регистрирует задачи и создаёт ресурсы worker (httpx-клиент, движок и сессии БД)."""
    register_tasks(broker)

    @broker.on_event(TaskiqEvents.WORKER_STARTUP)
    async def _startup(state: TaskiqState) -> None:
        state.http = httpx.AsyncClient(timeout=10, transport=transport)
        state.revalidator = HttpRevalidator(
            state.http, settings.revalidate_url, settings.revalidate_secret.get_secret_value()
        )
        # Движок ленивый: к БД подключается первая задача, а не старт worker.
        state.engine = create_db_engine(settings)
        state.sessionmaker = create_sessionmaker(state.engine)

    @broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
    async def _shutdown(state: TaskiqState) -> None:
        await state.http.aclose()
        await state.engine.dispose()

    return broker
