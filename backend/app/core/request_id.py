import json
import re
import time
from contextvars import ContextVar
from uuid import uuid4

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_body
from app.core.observability import scrub_text

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

# Пробы Docker/мониторинга дёргают эти пути постоянно — на INFO это шум.
_QUIET_PATHS = frozenset({"/api/health", "/api/health/ready"})

log = structlog.get_logger("app.http")


def get_request_id() -> str | None:
    return _request_id.get()


def _loggable_path(path: str) -> str:
    # Правила маскирования токенов общие с Sentry (app.core.observability).
    return scrub_text(path)


def _incoming_id(scope: Scope) -> str | None:
    for name, value in scope["headers"]:
        if name == b"x-request-id":
            candidate = value.decode("latin-1")
            return candidate if _VALID_ID.fullmatch(candidate) else None
    return None


class RequestIdMiddleware:
    """Сквозной X-Request-ID, access-лог и последний рубеж для непойманных исключений."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        rid = _incoming_id(scope) or uuid4().hex
        _request_id.set(rid)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid)

        started = time.perf_counter()
        status = 500
        response_started = False

        async def send_with_id(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = rid
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            log.exception("unhandled_error")
            if response_started:
                raise
            await self._send_internal_error(send, rid)
        finally:
            access_log = log.debug if scope["path"] in _QUIET_PATHS else log.info
            access_log(
                "http_request",
                method=scope["method"],
                path=_loggable_path(scope["path"]),
                status=status,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )

    @staticmethod
    async def _send_internal_error(send: Send, rid: str) -> None:
        body = json.dumps(
            error_body("internal_error", "Внутренняя ошибка сервера", {"request_id": rid}),
            ensure_ascii=False,
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (REQUEST_ID_HEADER.lower().encode(), rid.encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
