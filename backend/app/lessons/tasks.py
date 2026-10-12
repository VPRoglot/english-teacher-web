from datetime import UTC, datetime
from typing import Annotated

import structlog
from taskiq import AsyncBroker, Context, TaskiqDepends

from app.core.observability import ping_heartbeat
from app.lessons.generation import materialize_all

log = structlog.get_logger("app.lessons")

MATERIALIZE_SERIES_TASK = "lessons.materialize_series"
MATERIALIZE_SERIES_CRON = "0 1 * * *"  # ежедневно в 01:00 UTC


async def materialize_series_task(context: Annotated[Context, TaskiqDepends()]) -> None:
    """Доводит расписание активных серий до горизонта. Идемпотентна: повтор ничего не дублирует."""
    created = await materialize_all(context.state.sessionmaker, now=datetime.now(UTC))
    log.info("series_materialized", created=created)
    await ping_heartbeat(
        context.state.http, context.state.heartbeat_materialize_url, name="materialize_series"
    )


def register_tasks(broker: AsyncBroker) -> None:
    broker.register_task(
        materialize_series_task,
        task_name=MATERIALIZE_SERIES_TASK,
        retry_on_error=True,
        max_retries=5,
        schedule=[{"cron": MATERIALIZE_SERIES_CRON}],
    )
