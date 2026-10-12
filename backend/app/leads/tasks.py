from datetime import UTC, datetime
from typing import Annotated

import structlog
from taskiq import AsyncBroker, Context, TaskiqDepends

from app.core.observability import ping_heartbeat
from app.leads.retention import anonymize_stale_leads

log = structlog.get_logger("app.leads")

ANONYMIZE_LEADS_TASK = "leads.anonymize_stale"
ANONYMIZE_LEADS_CRON = "30 1 * * *"  # ежедневно в 01:30 UTC


async def anonymize_leads_task(context: Annotated[Context, TaskiqDepends()]) -> None:
    """Обезличивает заявки без движения 12 месяцев. Идемпотентна: повтор ничего не меняет."""
    async with context.state.sessionmaker() as session:
        count = await anonymize_stale_leads(session, now=datetime.now(UTC))
        await session.commit()
    log.info("leads_anonymized", count=count)
    await ping_heartbeat(
        context.state.http, context.state.heartbeat_anonymize_url, name="anonymize_leads"
    )


def register_tasks(broker: AsyncBroker) -> None:
    broker.register_task(
        anonymize_leads_task,
        task_name=ANONYMIZE_LEADS_TASK,
        retry_on_error=True,
        max_retries=5,
        schedule=[{"cron": ANONYMIZE_LEADS_CRON}],
    )
