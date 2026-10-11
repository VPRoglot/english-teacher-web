from typing import Any

import pytest
import structlog
from fastapi import FastAPI
from httpx import AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.redis import get_redis
from app.core.tasks import get_task_queue
from app.leads.models import Lead
from tests.conftest import FakeTaskQueue
from tests.leads.conftest import FakeCaptcha, valid_lead

URL = "/api/public/leads"
pytestmark = pytest.mark.usefixtures("captcha")


async def _count(db_session: AsyncSession) -> int:
    return await db_session.scalar(select(func.count(Lead.id))) or 0


async def test_submit_saves_lead_with_consent_utm_history_and_enqueues(
    client: AsyncClient, db_session: AsyncSession, task_queue: FakeTaskQueue
) -> None:
    r = await client.post(URL, json=valid_lead(utm_source="vk", phone="8 (999) 123-45-67"))
    assert r.status_code == 201 and r.json() == {"accepted": True}
    lead = (await db_session.execute(select(Lead).options(selectinload(Lead.history)))).scalar_one()
    assert lead.phone == "+79991234567" and lead.utm_source == "vk" and lead.status == "new"
    assert lead.consent_at is not None
    assert [(h.from_status, h.to_status) for h in lead.history] == [(None, "new")]
    assert task_queue.calls == [("notifications.notify_new_lead", {"lead_id": str(lead.id)})]


async def test_optional_fields_are_saved_and_blank_handle_becomes_null(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    body = valid_lead(
        messenger_handle="  ",
        goal="Подготовка к экзамену",
        preferred_time="вечером",
        utm_medium="cpc",
        utm_campaign="autumn",
    )
    assert (await client.post(URL, json=body)).status_code == 201
    lead = (await db_session.execute(select(Lead))).scalar_one()
    assert lead.messenger_handle is None
    assert (lead.goal, lead.preferred_time) == ("Подготовка к экзамену", "вечером")
    assert (lead.utm_medium, lead.utm_campaign) == ("cpc", "autumn")


@pytest.mark.parametrize(
    ("raw", "stored"),
    [
        ("@olga_test", "olga_test"),
        ("https://t.me/olga_test", "olga_test"),
        ("t.me/olga_test", "olga_test"),
        ("olga test", "olga test"),  # нестандартный ввод не теряет заявку
        ("@", None),
    ],
)
async def test_messenger_handle_is_normalized(
    client: AsyncClient, db_session: AsyncSession, raw: str, stored: str | None
) -> None:
    assert (await client.post(URL, json=valid_lead(messenger_handle=raw))).status_code == 201
    lead = (await db_session.execute(select(Lead))).scalar_one()
    assert lead.messenger_handle == stored


async def test_rate_limiter_outage_does_not_lose_the_lead(
    app: FastAPI,
    client: AsyncClient,
    db_session: AsyncSession,
    task_queue: FakeTaskQueue,
) -> None:
    class DownRedis:
        def pipeline(self, *args: Any, **kwargs: Any) -> Any:
            raise RedisConnectionError("redis недоступен")

        async def get(self, *args: Any, **kwargs: Any) -> Any:
            raise RedisConnectionError("redis недоступен")

    app.dependency_overrides[get_redis] = lambda: DownRedis()
    with structlog.testing.capture_logs() as logs:
        r = await client.post(URL, json=valid_lead())
    assert r.status_code == 201 and r.json() == {"accepted": True}
    assert await _count(db_session) == 1
    assert len(task_queue.calls) == 1
    unavailable = [e for e in logs if e["event"] == "lead_rate_limit_unavailable"]
    assert len(unavailable) == 1 and unavailable[0]["log_level"] == "warning"
    assert unavailable[0]["exc_info"] is True


async def test_captcha_receives_token_and_client_ip(
    client: AsyncClient, captcha: FakeCaptcha
) -> None:
    await client.post(URL, json=valid_lead(captcha_token="abc"))
    assert captcha.calls == [("abc", "127.0.0.1")]


async def test_fourth_lead_from_same_ip_in_an_hour_is_429(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    for _ in range(3):
        assert (await client.post(URL, json=valid_lead())).status_code == 201
    r = await client.post(URL, json=valid_lead())
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["Retry-After"]) > 0
    assert await _count(db_session) == 3


async def test_honeypot_counts_against_rate_limit(client: AsyncClient) -> None:
    for _ in range(3):
        r = await client.post(URL, json=valid_lead(website="http://spam.example"))
        assert r.status_code == 201
    assert (await client.post(URL, json=valid_lead())).status_code == 429


async def test_honeypot_pretends_success_but_stores_nothing(
    client: AsyncClient, db_session: AsyncSession, task_queue: FakeTaskQueue, captcha: FakeCaptcha
) -> None:
    with structlog.testing.capture_logs() as logs:
        r = await client.post(URL, json=valid_lead(website="http://spam.example"))
    assert r.status_code == 201 and r.json() == {"accepted": True}
    assert await _count(db_session) == 0 and task_queue.calls == []
    assert captcha.calls == []
    honeypot = [e for e in logs if e["event"] == "lead_honeypot"]
    assert len(honeypot) == 1 and honeypot[0]["log_level"] == "info"


async def test_failed_captcha_is_400_and_nothing_saved(
    client: AsyncClient, db_session: AsyncSession, captcha: FakeCaptcha, task_queue: FakeTaskQueue
) -> None:
    captcha.result = False
    r = await client.post(URL, json=valid_lead())
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "captcha_failed"
    assert r.json()["error"]["message"].startswith("Не удалось подтвердить")
    assert await _count(db_session) == 0 and task_queue.calls == []


async def test_consent_is_required(client: AsyncClient) -> None:
    r = await client.post(URL, json=valid_lead(consent=False))
    assert r.status_code == 422
    (field,) = r.json()["error"]["details"]["fields"]
    assert field["loc"] == ["body", "consent"]
    assert field["message"] == "Нужно согласие на обработку персональных данных"


async def test_invalid_phone_error_is_on_phone_field(client: AsyncClient) -> None:
    r = await client.post(URL, json=valid_lead(phone="12345"))
    (field,) = r.json()["error"]["details"]["fields"]
    assert field["loc"] == ["body", "phone"]
    assert field["message"] == "Укажите телефон в формате +7 999 123-45-67"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("child_age", 2),
        ("child_age", 19),
        ("phone", "12345"),
        ("contact_method", "email"),
        ("parent_name", "  "),
        ("child_name", ""),
        ("parent_name", "x" * 101),
        ("goal", "x" * 1001),
        ("preferred_time", "x" * 201),
        ("messenger_handle", "x" * 65),
        ("utm_source", "x" * 101),
        ("captcha_token", "x" * 5001),
        ("website", "x" * 201),
        ("unknown_field", "x"),
    ],
)
async def test_invalid_fields_are_422(
    client: AsyncClient, db_session: AsyncSession, field: str, value: Any
) -> None:
    r = await client.post(URL, json=valid_lead(**{field: value}))
    assert r.status_code == 422
    assert await _count(db_session) == 0


async def test_invalid_body_does_not_consume_rate_limit(client: AsyncClient) -> None:
    for _ in range(5):
        assert (await client.post(URL, json=valid_lead(child_age=1))).status_code == 422
    assert (await client.post(URL, json=valid_lead())).status_code == 201


async def test_lead_saved_even_if_enqueue_fails(
    client: AsyncClient, db_session: AsyncSession, task_queue: FakeTaskQueue
) -> None:
    task_queue.fail = True
    with structlog.testing.capture_logs() as logs:
        r = await client.post(URL, json=valid_lead())
    assert r.status_code == 201 and r.json() == {"accepted": True}
    assert await _count(db_session) == 1
    failed = [e for e in logs if e["event"] == "lead_notification_enqueue_failed"]
    assert len(failed) == 1 and failed[0]["log_level"] == "warning"


async def test_task_is_enqueued_after_commit(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    real_commit = db_session.commit

    async def commit() -> None:
        events.append("commit")
        await real_commit()

    class RecordingQueue:
        async def enqueue(self, task_name: str, /, **kwargs: Any) -> None:
            events.append("enqueue")

    monkeypatch.setattr(db_session, "commit", commit)
    app.dependency_overrides[get_task_queue] = lambda: RecordingQueue()
    assert (await client.post(URL, json=valid_lead())).status_code == 201
    assert events[:2] == ["commit", "enqueue"]
