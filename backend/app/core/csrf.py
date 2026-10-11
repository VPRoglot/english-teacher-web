import hmac
import re
import secrets

from fastapi import APIRouter, Request, Response
from starlette.requests import cookie_parser
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.errors import API_ERROR_RESPONSES, error_body

CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

_API_PREFIX = "/api/"
_CSRF_HEADER_RAW = CSRF_HEADER.lower().encode()
_VALID_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")  # secrets.token_urlsafe(32)


def _request_tokens(scope: Scope) -> tuple[str, str]:
    """Токен из cookie и из заголовка (пустая строка, если нет)."""
    header = ""
    cookie_header = ""
    for name, value in scope["headers"]:
        if name == _CSRF_HEADER_RAW:
            header = value.decode("latin-1")
        elif name == b"cookie":
            cookie_header = f"{cookie_header}; {value.decode('latin-1')}"
    return cookie_parser(cookie_header).get(CSRF_COOKIE, ""), header


class CsrfMiddleware:
    """Double-submit CSRF: небезопасным запросам к /api/ нужны cookie и равный ей заголовок."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] in SAFE_METHODS
            or not scope["path"].startswith(_API_PREFIX)
        ):
            await self.app(scope, receive, send)
            return

        cookie_token, header_token = _request_tokens(scope)
        # Сравнение байтов: для str с не-ASCII символами compare_digest бросает TypeError.
        if (
            cookie_token
            and header_token
            and hmac.compare_digest(cookie_token.encode(), header_token.encode())
        ):
            await self.app(scope, receive, send)
            return

        response = JSONResponse(
            error_body("csrf_failed", "Сессия страницы устарела. Обновите страницу и повторите."),
            status_code=403,
        )
        await response(scope, receive, send)


router = APIRouter(tags=["auth"], responses=API_ERROR_RESPONSES)


@router.get("/auth/csrf", status_code=204, response_class=Response)
async def get_csrf(request: Request) -> Response:
    """Выдаёт CSRF-токен в cookie (читаемой из JS); уже выданный не меняет."""
    response = Response(status_code=204)
    existing = request.cookies.get(CSRF_COOKIE, "")
    if not _VALID_TOKEN.fullmatch(existing):
        response.set_cookie(
            CSRF_COOKIE,
            secrets.token_urlsafe(32),
            httponly=False,
            secure=request.app.state.settings.session_cookie_secure,
            samesite="lax",
            path="/",
        )
    return response
