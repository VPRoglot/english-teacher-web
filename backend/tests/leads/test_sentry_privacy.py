"""Ошибка 500 на публичной форме не уносит в Sentry тело запроса и локальные переменные."""

from collections.abc import Iterator
from typing import Any

import pytest
import sentry_sdk
from fastapi import FastAPI
from pydantic import SecretStr

from app.core import observability
from app.core.config import Settings
from tests.conftest import open_client
from tests.core.test_observability import DSN, CollectingTransport
from tests.leads.conftest import valid_lead

pytestmark = pytest.mark.usefixtures("captcha")


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"sentry_dsn": SecretStr(DSN)})


@pytest.fixture(autouse=True)
def transport(monkeypatch: pytest.MonkeyPatch) -> Iterator[CollectingTransport]:
    """create_app включает Sentry сам — подставляем транспорт, собирающий события."""
    collecting = CollectingTransport()
    real_init = observability.init_sentry

    def init_with_transport(settings: Settings, component: Any) -> bool:
        return real_init(settings, component, transport=collecting)

    monkeypatch.setattr("app.main.init_sentry", init_with_transport)
    yield collecting
    sentry_sdk.get_client().close()
    sentry_sdk.get_global_scope().clear()
    sentry_sdk.get_isolation_scope().clear()
    sentry_sdk.get_current_scope().clear()
    # Неактивный клиент, как до первого init: test_init_without_dsn_is_noop не зависит от порядка.
    sentry_sdk.get_global_scope().set_client(None)


async def test_server_error_event_has_no_request_body_or_local_vars(
    app: FastAPI, transport: CollectingTransport, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken_create_lead(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("app.leads.service.create_lead", broken_create_lead)
    async with open_client(app, raise_app_exceptions=False) as client:
        r = await client.post("/api/public/leads", json=valid_lead(phone="+7 999 765-43-21"))
    assert r.status_code == 500

    (event,) = [e for e in transport.events if "exception" in e]
    assert not event["request"].get("data")  # при "never" SDK оставляет пустую строку
    frames = [f for v in event["exception"]["values"] for f in v["stacktrace"]["frames"]]
    assert frames and all("vars" not in f for f in frames)
    # Телефон после валидации живёт только в локальных переменных обработчика.
    assert "79997654321" not in repr(event)
