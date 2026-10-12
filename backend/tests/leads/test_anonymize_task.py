from datetime import UTC, datetime
from typing import Any

import pytest
import structlog
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession
from taskiq import Context, InMemoryBroker

from app.leads.models import Lead
from app.leads.tasks import ANONYMIZE_LEADS_CRON, ANONYMIZE_LEADS_TASK, anonymize_leads_task
from app.tasks import setup_worker
from tests.conftest import make_settings
from tests.leads.conftest import make_lead


def test_task_is_registered_with_daily_cron() -> None:
    assert ANONYMIZE_LEADS_TASK == "leads.anonymize_stale"
    assert ANONYMIZE_LEADS_CRON == "30 1 * * *"
    broker = setup_worker(InMemoryBroker(), make_settings())
    task = broker.find_task(ANONYMIZE_LEADS_TASK)
    assert task is not None
    assert task.labels["schedule"] == [{"cron": "30 1 * * *"}]
    assert task.labels["retry_on_error"] is True
    assert task.labels["max_retries"] == 5


async def test_anonymize_task_commits_and_pings(
    context: Context, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    lead = await make_lead(db_session, created_at=datetime(2020, 1, 1, tzinfo=UTC))
    url = SecretStr("https://hc.example/ping/anon")
    context.state.heartbeat_anonymize_url = url
    pings: list[tuple[Any, Any, str]] = []

    async def fake_ping(http: Any, ping_url: Any, *, name: str) -> None:
        pings.append((http, ping_url, name))

    monkeypatch.setattr("app.leads.tasks.ping_heartbeat", fake_ping)

    with structlog.testing.capture_logs() as logs:
        await anonymize_leads_task(context)

    await db_session.refresh(lead)
    assert lead.anonymized_at is not None
    assert lead.parent_name == "Обезличено"
    assert [(e["event"], e["log_level"], e["count"]) for e in logs] == [
        ("leads_anonymized", "info", 1)
    ]
    assert pings == [(context.state.http, url, "anonymize_leads")]
    assert isinstance(lead, Lead)


async def test_anonymize_task_failure_sends_no_heartbeat(
    context: Context, monkeypatch: pytest.MonkeyPatch
) -> None:
    pings: list[str] = []

    async def fake_ping(http: Any, ping_url: Any, *, name: str) -> None:
        pings.append(name)

    async def failing(*_a: Any, **_k: Any) -> int:
        raise RuntimeError("db down")

    monkeypatch.setattr("app.leads.tasks.ping_heartbeat", fake_ping)
    monkeypatch.setattr("app.leads.tasks.anonymize_stale_leads", failing)

    with pytest.raises(RuntimeError):
        await anonymize_leads_task(context)

    assert pings == []
