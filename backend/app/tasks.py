import httpx
from taskiq import AsyncBroker, TaskiqEvents, TaskiqState

from app.core.config import Settings
from app.core.db import create_db_engine, create_sessionmaker
from app.core.observability import SentryTaskMiddleware, init_sentry
from app.leads import tasks as lead_tasks
from app.lessons import tasks as lesson_tasks
from app.notifications import tasks as notification_tasks
from app.notifications.notifier import DisabledNotifier, Notifier, TelegramNotifier
from app.site_content import tasks as site_content_tasks
from app.site_content.tasks import HttpRevalidator


def setup_worker(
    broker: AsyncBroker,
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AsyncBroker:
    """Регистрирует задачи и создаёт ресурсы worker (httpx-клиент, движок, сессии БД, notifier)."""
    broker.add_middlewares(SentryTaskMiddleware())
    site_content_tasks.register_tasks(broker)
    notification_tasks.register_tasks(broker)
    lesson_tasks.register_tasks(broker)
    lead_tasks.register_tasks(broker)

    @broker.on_event(TaskiqEvents.WORKER_STARTUP)
    async def _startup(state: TaskiqState) -> None:
        init_sentry(settings, "worker")
        state.http = httpx.AsyncClient(timeout=10, transport=transport)
        state.revalidator = HttpRevalidator(
            state.http, settings.revalidate_url, settings.revalidate_secret.get_secret_value()
        )
        notifier: Notifier = DisabledNotifier()
        if settings.telegram_bot_token and settings.telegram_chat_id:
            notifier = TelegramNotifier(
                state.http,
                settings.telegram_bot_token.get_secret_value(),
                settings.telegram_chat_id,
            )
        state.notifier = notifier
        state.public_base_url = settings.public_base_url
        state.heartbeat_materialize_url = settings.heartbeat_materialize_url
        state.heartbeat_anonymize_url = settings.heartbeat_anonymize_url
        # Движок ленивый: к БД подключается первая задача, а не старт worker.
        state.engine = create_db_engine(settings)
        state.sessionmaker = create_sessionmaker(state.engine)

    @broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
    async def _shutdown(state: TaskiqState) -> None:
        await state.http.aclose()
        await state.engine.dispose()

    return broker
