from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_body
from app.site_content.errors import FileTooLarge
from app.site_content.images import MAX_UPLOAD_BYTES

UPLOAD_PATH = "/api/admin/media"
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 1024 * 1024  # файл + накладные расходы multipart


class UploadTooLargeError(Exception):
    """Тело запроса превысило лимит, а ответ уже начат: соединение рвём."""


class UploadLimitMiddleware:
    """Отсекает слишком большую загрузку до разбора multipart.

    FastAPI разбирает тело раньше зависимостей, поэтому без этого слоя аноним может
    заставить Starlette складывать на диск тело любого размера ещё до ответа 401.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int = MAX_REQUEST_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != UPLOAD_PATH:
            await self.app(scope, receive, send)
            return

        if self._declared_length(scope) > self.max_bytes:
            await self._reject(scope, receive, send)
            return

        received = 0
        exceeded = False
        started = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            if exceeded:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    exceeded = True
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal started
            if exceeded and not started:
                return  # ответ приложения на оборванное тело (400/500) заменит наш 413
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except Exception:
            if not exceeded:
                raise
        if exceeded:
            if started:
                raise UploadTooLargeError
            await self._reject(scope, receive, send)

    @staticmethod
    def _declared_length(scope: Scope) -> int:
        for name, value in scope["headers"]:
            if name == b"content-length":
                try:
                    return int(value)
                except ValueError:
                    return 0
        return 0

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            error_body(FileTooLarge.code, FileTooLarge.message),
            status_code=FileTooLarge.status_code,
            headers={"Connection": "close"},
        )
        await response(scope, receive, send)
