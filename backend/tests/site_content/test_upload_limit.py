from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.site_content.images import MAX_UPLOAD_BYTES
from app.site_content.upload_limit import (
    MAX_REQUEST_BYTES,
    UploadLimitMiddleware,
    UploadTooLargeError,
)
from tests.conftest import open_client
from tests.site_content.conftest import make_image

MIB = 1024 * 1024
_MULTIPART = "multipart/form-data; boundary=x"


class _BodyReadSpy:
    """ASGI-обёртка: считает байты тела, которые приложение реально получило."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.body_bytes = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def spying_receive() -> Message:
            message = await receive()
            if scope.get("path") == "/api/admin/media" and message["type"] == "http.request":
                self.body_bytes += len(message.get("body", b""))
            return message

        await self.app(scope, spying_receive, send)


_FILE_PART_HEAD = (
    b'--x\r\nContent-Disposition: form-data; name="file"; filename="a.jpg"\r\n'
    b"Content-Type: image/jpeg\r\n\r\n"
)


async def _chunks(count: int) -> AsyncIterator[bytes]:
    """Начало настоящего multipart с файлом и затем count мегабайт данных."""
    yield _FILE_PART_HEAD
    for _ in range(count):
        yield b"\xff" * MIB


async def test_anonymous_huge_content_length_is_413_and_body_unread(app: FastAPI) -> None:
    spy = _BodyReadSpy(app)
    async with open_client(app, asgi=spy) as c:
        r = await c.post("/api/admin/media", content=b"\xff" * (MAX_REQUEST_BYTES + 1))
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "file_too_large"
    assert spy.body_bytes == 0


async def test_streamed_body_over_cap_without_content_length_is_413(app: FastAPI) -> None:
    spy = _BodyReadSpy(app)
    async with open_client(app, asgi=spy) as c:
        request = c.build_request(
            "POST", "/api/admin/media", content=_chunks(20), headers={"Content-Type": _MULTIPART}
        )
        assert "content-length" not in request.headers
        r = await c.send(request)
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "file_too_large"
    assert MAX_REQUEST_BYTES < spy.body_bytes <= MAX_REQUEST_BYTES + MIB  # чтение остановлено


async def test_streamed_body_under_cap_reaches_the_handler(tutor_client: AsyncClient) -> None:
    async def body() -> AsyncIterator[bytes]:
        yield b"x" * 100

    request = tutor_client.build_request(
        "POST", "/api/admin/media", content=body(), headers={"Content-Type": "text/plain"}
    )
    r = await tutor_client.send(request)
    assert r.status_code == 422  # дошло до FastAPI: нет поля file


async def test_normal_upload_still_201(tutor_client: AsyncClient) -> None:
    r = await tutor_client.post(
        "/api/admin/media",
        files={"file": ("a.jpg", make_image("JPEG", (50, 50)), "image/jpeg")},
    )
    assert r.status_code == 201


async def test_other_paths_are_not_limited(client: AsyncClient) -> None:
    r = await client.post("/api/auth/login", content=b"x" * (MAX_REQUEST_BYTES + 1))
    assert r.status_code != 413


async def test_file_just_over_5_mb_still_gets_in_handler_413(tutor_client: AsyncClient) -> None:
    # тело укладывается в лимит middleware (5 МБ + запас), отказ даёт проверка в обработчике
    r = await tutor_client.post(
        "/api/admin/media",
        files={"file": ("big.jpg", b"\xff" * (MAX_UPLOAD_BYTES + 1), "image/jpeg")},
    )
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "file_too_large"


async def test_response_already_started_aborts_the_connection() -> None:
    async def greedy_app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        while (await receive())["type"] == "http.request":
            pass

    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    chunks = iter([{"type": "http.request", "body": b"x" * 20, "more_body": True}] * 3)

    async def receive() -> Message:
        return next(chunks)

    scope: Scope = {"type": "http", "method": "POST", "path": "/api/admin/media", "headers": []}
    middleware = UploadLimitMiddleware(greedy_app, max_bytes=30)
    with pytest.raises(UploadTooLargeError):
        await middleware(scope, receive, send)
    assert [m["type"] for m in sent] == ["http.response.start"]  # 413 поверх начатого не шлём


def _post_scope(headers: list[tuple[bytes, bytes]]) -> Scope:
    return {"type": "http", "method": "POST", "path": "/api/admin/media", "headers": headers}


async def test_app_failure_on_cut_body_is_replaced_by_413() -> None:
    async def failing_app(scope: Scope, receive: Receive, send: Send) -> None:
        while (await receive())["type"] == "http.request":
            pass
        raise RuntimeError("тело оборвано")

    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    chunks = iter([{"type": "http.request", "body": b"x" * 20, "more_body": True}] * 3)

    async def receive() -> Message:
        return next(chunks)

    await UploadLimitMiddleware(failing_app, max_bytes=30)(_post_scope([]), receive, send)
    assert sent[0]["status"] == 413


async def test_unparsable_content_length_is_left_to_the_stream_counter() -> None:
    reached = False

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        nonlocal reached
        reached = True

    async def receive() -> Message:
        raise AssertionError("не должно читаться")

    async def send(message: Message) -> None:
        raise AssertionError("не должно отвечать")

    scope = _post_scope([(b"content-length", b"abc")])
    await UploadLimitMiddleware(app, max_bytes=30)(scope, receive, send)
    assert reached
