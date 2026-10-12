from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import sentry_sdk
import structlog
from pydantic import SecretStr
from sentry_sdk.transport import Transport
from taskiq import TaskiqMessage, TaskiqResult

from app.core.observability import (
    SentryTaskMiddleware,
    init_sentry,
    ping_heartbeat,
    scrub_breadcrumb,
    scrub_event,
    scrub_text,
)
from tests.conftest import make_settings

DSN = "https://public@o0.ingest.sentry.io/1"


class CollectingTransport(Transport):
    def __init__(self, options: dict[str, Any] | None = None) -> None:
        super().__init__(options)
        self.events: list[dict[str, Any]] = []

    def capture_envelope(self, envelope: Any) -> None:
        event = envelope.get_event()
        if event is not None:
            self.events.append(event)


@pytest.fixture(autouse=True)
def reset_sentry() -> Iterator[None]:
    """init_sentry меняет глобальное состояние SDK — возвращаем его для остальных тестов."""
    yield
    sentry_sdk.get_client().close()
    sentry_sdk.get_global_scope().clear()
    sentry_sdk.get_isolation_scope().clear()
    sentry_sdk.get_current_scope().clear()
    sentry_sdk.init()


def test_init_without_dsn_is_noop() -> None:
    assert init_sentry(make_settings(sentry_dsn=None), "api") is False
    assert not sentry_sdk.get_client().is_active()


def test_init_with_dsn_sets_tags() -> None:
    transport = CollectingTransport()
    settings = make_settings(sentry_dsn=DSN, app_env="test", release="abc123")

    assert init_sentry(settings, "api", transport=transport) is True
    sentry_sdk.capture_message("x")

    (event,) = transport.events
    assert event["environment"] == "test"
    assert event["release"] == "abc123"
    assert event["tags"]["component"] == "api"
    assert sentry_sdk.get_client().options["send_default_pii"] is False


def test_release_is_read_from_image_tag_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMAGE_TAG", "sha-42")
    assert make_settings().release == "sha-42"


def test_traces_sample_rate_is_validated() -> None:
    with pytest.raises(ValueError, match="sentry_traces_sample_rate"):
        make_settings(sentry_traces_sample_rate=1.5)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/invite/AbC_123-x", "/invite/***"),
        ("/reset/tok", "/reset/***"),
        ("/api/auth/invitations/tok/accept", "/api/auth/invitations/***/accept"),
        ("/api/auth/password-resets/tok", "/api/auth/password-resets/***"),
        (
            "https://api.telegram.org/bot123:AAx/sendMessage",
            "https://api.telegram.org/bot***/sendMessage",
        ),
        ("https://site.ru/invite/tok?x=1", "https://site.ru/invite/***?x=1"),
        ("/api/health", "/api/health"),
        ("обычный текст", "обычный текст"),
    ],
)
def test_scrub_text(raw: str, expected: str) -> None:
    assert scrub_text(raw) == expected


def test_scrub_event_masks_request_url_and_breadcrumbs() -> None:
    event: Any = {
        "transaction": "/api/auth/invitations/tok1/accept",
        "request": {
            "url": "https://site.ru/invite/tok2",
            "cookies": {"session": "s"},
            "headers": {"Cookie": "session=s", "X-CSRF-Token": "c", "Accept": "*/*"},
        },
        "breadcrumbs": {
            "values": [
                {"message": "GET /reset/tok3"},
                {"category": "httpx", "data": {"url": "https://api.telegram.org/bot1:AA/send"}},
            ]
        },
    }

    result: Any = scrub_event(event, {})

    assert result["transaction"] == "/api/auth/invitations/***/accept"
    assert result["request"]["url"] == "https://site.ru/invite/***"
    assert "cookies" not in result["request"]
    assert result["request"]["headers"] == {"Accept": "*/*"}
    crumbs = result["breadcrumbs"]["values"]
    assert crumbs[0]["message"] == "GET /reset/***"
    assert crumbs[1]["data"]["url"] == "https://api.telegram.org/bot***/send"


def test_scrub_breadcrumb_httpx_token() -> None:
    crumb: Any = {"category": "httpx", "data": {"url": "https://api.telegram.org/bot123:AA/send"}}
    result: Any = scrub_breadcrumb(crumb, {})
    assert result["data"]["url"] == "https://api.telegram.org/bot***/send"


def test_task_middleware_captures_error() -> None:
    transport = CollectingTransport()
    init_sentry(make_settings(sentry_dsn=DSN), "worker", transport=transport)
    message = TaskiqMessage(task_id="t1", task_name="leads.notify", labels={}, args=[], kwargs={})
    result: TaskiqResult[Any] = TaskiqResult(
        is_err=True, return_value=None, execution_time=0.0, log=None
    )

    SentryTaskMiddleware().on_error(message, result, RuntimeError("boom"))

    (event,) = transport.events
    assert event["tags"]["task_name"] == "leads.notify"
    assert event["tags"]["component"] == "worker"
    assert event["exception"]["values"][0]["type"] == "RuntimeError"


HEARTBEAT = SecretStr("https://hc.example/ping/secret-uuid")


async def test_ping_heartbeat_without_url_does_nothing() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await ping_heartbeat(http, None, name="job")
    assert requests == []


async def test_ping_heartbeat_sends_one_get() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await ping_heartbeat(http, HEARTBEAT, name="job")
    assert [(r.method, str(r.url)) for r in requests] == [("GET", HEARTBEAT.get_secret_value())]


@pytest.mark.parametrize("failure", ["status", "network"])
async def test_ping_heartbeat_failure_is_logged_not_raised(failure: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "network":
            raise httpx.ConnectError("down", request=request)
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with structlog.testing.capture_logs() as logs:
            await ping_heartbeat(http, HEARTBEAT, name="job")

    assert [(e["event"], e["name"], e["log_level"]) for e in logs] == [
        ("heartbeat_failed", "job", "warning")
    ]
    assert "secret-uuid" not in repr(logs)
