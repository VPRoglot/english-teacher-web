import logging
from collections.abc import Iterator

import httpx
import pytest

from app.core.logging import configure_logging
from app.notifications.notifier import TelegramNotifier

TOKEN = "123456:SECRET-token"
_LOGGERS = ("", "httpx", "httpcore", "uvicorn", "uvicorn.error", "uvicorn.access")


@pytest.fixture
def restore_logging() -> Iterator[None]:
    """configure_logging меняет глобальные логгеры — возвращаем их как были."""
    saved = [
        (log, log.handlers[:], log.level, log.propagate, log.disabled)
        for log in map(logging.getLogger, _LOGGERS)
    ]
    yield
    for log, handlers, level, propagate, disabled in saved:
        log.handlers, log.propagate, log.disabled = handlers, propagate, disabled
        log.setLevel(level)


@pytest.mark.usefixtures("restore_logging")
async def test_bot_token_never_reaches_logs(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", True)
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": True}))

    async with httpx.AsyncClient(transport=transport) as client:
        await TelegramNotifier(client, TOKEN, "-1001").send("привет")

    captured = capsys.readouterr()
    assert TOKEN not in captured.out + captured.err


@pytest.mark.usefixtures("restore_logging")
def test_http_client_loggers_are_quiet_at_info() -> None:
    configure_logging("INFO", True)
    # URL запроса к Telegram содержит токен, а httpx пишет его на уровне INFO.
    assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() == logging.WARNING
