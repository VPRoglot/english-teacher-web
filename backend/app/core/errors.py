from http import HTTPStatus
from typing import Any, ClassVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Доменная ошибка; превращается в ответ `{"error": {...}}` с `status_code`."""

    status_code: ClassVar[int] = 400
    code: str = "bad_request"
    message: str = "Некорректный запрос"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or type(self).message
        self.code = code or type(self).code
        self.details = details or {}
        super().__init__(self.message)


class NotFound(AppError):
    status_code = 404
    code = "not_found"
    message = "Не найдено"


class Conflict(AppError):
    status_code = 409
    code = "conflict"
    message = "Конфликт"


class PermissionDenied(AppError):
    status_code = 403
    code = "permission_denied"
    message = "Доступ запрещён"


class ValidationFailed(AppError):
    status_code = 422
    code = "validation_error"
    message = "Ошибка валидации"


_HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}
_HTTP_MESSAGES = {404: "Не найдено", 405: "Метод не поддерживается"}


def _http_message(exc: StarletteHTTPException) -> str:
    """Свой текст `detail` сохраняется; стандартная английская фраза Starlette — нет."""
    default_phrase = HTTPStatus(exc.status_code).phrase
    if isinstance(exc.detail, str) and exc.detail != default_phrase:
        return exc.detail
    return _HTTP_MESSAGES.get(exc.status_code, "Ошибка запроса")


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(error_body(exc.code, exc.message, exc.details), exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"loc": list(e["loc"]), "message": e["msg"], "type": e["type"]} for e in exc.errors()
        ]
        body = error_body(ValidationFailed.code, ValidationFailed.message, {"fields": fields})
        return JSONResponse(body, 422)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        body = error_body(code, _http_message(exc))
        return JSONResponse(body, exc.status_code, headers=exc.headers)
