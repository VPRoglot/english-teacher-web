"""Sentry для api, worker и scheduler, маскирование токенов и heartbeat-пинги ежедневных задач."""

import re
from typing import TYPE_CHECKING, Any, Literal, cast

import httpx
import sentry_sdk
import structlog
from pydantic import SecretStr
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from app.core.config import Settings

if TYPE_CHECKING:
    from sentry_sdk._types import Breadcrumb, Event, Hint

log = structlog.get_logger("app.observability")

_MASK = "***"
# Одноразовые токены из ссылок и токен Telegram-бота в URL не должны попадать в логи и в Sentry.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(/(?:invite|reset|api/auth/invitations|api/auth/password-resets)/)[^/?#\s\"']+"),
    re.compile(r"(api\.telegram\.org/bot)[^/?#\s\"']+"),
)
_DROPPED_HEADERS = frozenset({"cookie", "set-cookie", "authorization", "x-csrf-token"})
_HEARTBEAT_TIMEOUT = 10.0


def scrub_text(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(rf"\1{_MASK}", text)
    return text


def _scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        return {key: _scrub_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub_value(item) for item in value]
    return value


def _drop_secret_headers(request: dict[str, Any]) -> None:
    request.pop("cookies", None)
    headers = request.get("headers")
    if isinstance(headers, dict):
        request["headers"] = {k: v for k, v in headers.items() if k.lower() not in _DROPPED_HEADERS}


def scrub_event(event: "Event", hint: "Hint") -> "Event | None":
    data = cast(dict[str, Any], _scrub_value(dict(event)))
    request = data.get("request")
    if isinstance(request, dict):
        _drop_secret_headers(request)
    return cast("Event", data)


def scrub_breadcrumb(crumb: "Breadcrumb", hint: "Hint") -> "Breadcrumb | None":
    # httpx/httpcore молчат в логах (см. app.core.logging), но Sentry пишет из них breadcrumbs
    # с полным URL, а в URL Telegram Bot API лежит токен.
    return cast("Breadcrumb", _scrub_value(crumb))


def init_sentry(
    settings: Settings,
    component: Literal["api", "worker", "scheduler"],
    *,
    transport: Any = None,
) -> bool:
    """Включает Sentry, если задан DSN. Без DSN ничего не делает и возвращает False."""
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.app_env,
        release=settings.release,
        send_default_pii=False,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        before_send=scrub_event,
        before_breadcrumb=scrub_breadcrumb,
        transport=transport,
    )
    sentry_sdk.set_tag("component", component)
    return True


class SentryTaskMiddleware(TaskiqMiddleware):
    """У Taskiq нет официальной интеграции: ошибки задач отправляем сами."""

    def on_error(
        self, message: TaskiqMessage, result: TaskiqResult[Any], exception: BaseException
    ) -> None:
        with sentry_sdk.new_scope() as scope:
            scope.set_tag("task_name", message.task_name)
            scope.set_tag("task_id", message.task_id)
            sentry_sdk.capture_exception(exception)


async def ping_heartbeat(http: httpx.AsyncClient, url: SecretStr | None, *, name: str) -> None:
    """Сообщает внешнему монитору, что ежедневная задача отработала. Сбой пинга не роняет задачу."""
    if url is None:
        return
    try:
        response = await http.get(url.get_secret_value(), timeout=_HEARTBEAT_TIMEOUT)
        response.raise_for_status()
    except Exception as exc:
        # URL содержит секретный uuid: в лог идёт только имя и тип ошибки.
        log.warning("heartbeat_failed", name=name, error=type(exc).__name__)
