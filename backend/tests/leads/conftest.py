from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.leads.captcha import get_captcha_verifier
from app.leads.models import ContactMethod, Lead, LeadStatus, LeadStatusHistory
from tests.factories import login, make_family, make_parent, make_tutor


class FakeCaptcha:
    """Проверка капчи для API-тестов: запоминает вызовы и возвращает заданный результат."""

    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.calls: list[tuple[str | None, str | None]] = []

    async def verify(self, token: str | None, ip: str | None) -> bool:
        self.calls.append((token, ip))
        return self.result


@pytest.fixture
def captcha(app: FastAPI) -> FakeCaptcha:
    fake = FakeCaptcha(True)
    app.dependency_overrides[get_captcha_verifier] = lambda: fake
    return fake


@pytest.fixture
async def tutor_client(client: AsyncClient, db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    await make_tutor(db_session)
    await login(client, "tutor@example.com")
    yield client


@pytest.fixture
async def parent_client(
    client: AsyncClient, db_session: AsyncSession
) -> AsyncIterator[AsyncClient]:
    family = await make_family(db_session)
    await make_parent(db_session, family)
    await login(client, "parent@example.com")
    yield client


async def make_lead(session: AsyncSession, **overrides: Any) -> Lead:
    """Заявка в БД с первой строкой истории `None → status`; `overrides` заменяют поля.

    `created_at` по умолчанию — текущее время: server_default `now()` в тестовой транзакции
    одинаков для всех строк, и порядок списка был бы неопределённым.
    """
    now = datetime.now(UTC)
    values: dict[str, Any] = {
        "parent_name": "Анна",
        "child_name": "Маша",
        "child_age": 9,
        "phone": "+79991234567",
        "contact_method": ContactMethod.TELEGRAM,
        "status": LeadStatus.NEW,
        "consent_at": now,
        "created_at": now,
    }
    values.update(overrides)
    values["status"] = LeadStatus(values["status"])
    lead = Lead(**values)
    session.add(lead)
    await session.flush()
    session.add(
        LeadStatusHistory(
            lead_id=lead.id, from_status=None, to_status=lead.status, changed_at=lead.created_at
        )
    )
    await session.flush()
    return lead


def valid_lead(**overrides: Any) -> dict[str, Any]:
    """Тело валидной публичной заявки; `overrides` заменяют или добавляют поля."""
    body: dict[str, Any] = {
        "parent_name": "Анна",
        "child_name": "Маша",
        "child_age": 9,
        "phone": "+7 999 123-45-67",
        "contact_method": "telegram",
        "consent": True,
        "captcha_token": "token",
    }
    return {**body, **overrides}
