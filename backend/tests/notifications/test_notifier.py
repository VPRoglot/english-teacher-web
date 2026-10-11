import json

import httpx
import pytest
import structlog

from app.notifications.notifier import DisabledNotifier, NotifyFailed, TelegramNotifier

TOKEN = "123456:SECRET-token"
CHAT_ID = "-1001"


async def _send(transport: httpx.MockTransport, text: str = "привет") -> None:
    async with httpx.AsyncClient(transport=transport) as client:
        await TelegramNotifier(client, TOKEN, CHAT_ID).send(text)


async def test_telegram_posts_plain_text_without_parse_mode() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    await _send(httpx.MockTransport(handler), "<b>Анна</b> *_[x](y)")

    assert [(r.method, str(r.url)) for r in requests] == [
        ("POST", f"https://api.telegram.org/bot{TOKEN}/sendMessage")
    ]
    assert json.loads(requests[0].content) == {
        "chat_id": CHAT_ID,
        "text": "<b>Анна</b> *_[x](y)",
        "disable_web_page_preview": True,
    }


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(429),
        httpx.Response(200, json={"ok": False, "description": "chat not found"}),
        httpx.Response(200, text="not json"),
    ],
)
async def test_telegram_errors_raise_notify_failed_without_token(response: httpx.Response) -> None:
    with pytest.raises(NotifyFailed) as exc_info:
        await _send(httpx.MockTransport(lambda r: response))
    assert TOKEN not in str(exc_info.value)


async def test_telegram_network_error_raises_notify_failed_without_token() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        # httpx кладёт URL запроса (а в нём токен) в текст своей ошибки.
        raise httpx.ConnectError(f"refused {request.url}", request=request)

    with pytest.raises(NotifyFailed) as exc_info:
        await _send(httpx.MockTransport(refuse))
    assert TOKEN not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__  # токен не попадёт в traceback через контекст


async def test_disabled_notifier_logs_and_skips() -> None:
    with structlog.testing.capture_logs() as logs:
        await DisabledNotifier().send("текст")
    assert [(e["event"], e["log_level"]) for e in logs] == [("telegram_disabled", "warning")]
