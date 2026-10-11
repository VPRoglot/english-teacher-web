from typing import Protocol

import httpx
import structlog

log = structlog.get_logger("app.notifications")

TELEGRAM_API = "https://api.telegram.org"


class NotifyFailed(Exception):
    """Уведомление не доставлено: задача будет повторена."""


class Notifier(Protocol):
    async def send(self, text: str) -> None: ...


class TelegramNotifier(Notifier):
    def __init__(self, client: httpx.AsyncClient, token: str, chat_id: str) -> None:
        self._client = client
        self._token = token
        self._chat_id = chat_id

    async def send(self, text: str) -> None:
        # Без parse_mode: данные заявки приходят от посетителей и уходят обычным текстом.
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "link_preview_options": {"is_disabled": True},
        }
        try:
            response = await self._client.post(
                f"{TELEGRAM_API}/bot{self._token}/sendMessage", json=payload
            )
        except httpx.HTTPError as exc:
            # `from None`: httpx кладёт URL запроса, а в нём токен, в текст своей ошибки.
            raise NotifyFailed(f"Telegram недоступен: {type(exc).__name__}") from None
        if not response.is_success:
            raise NotifyFailed(f"Telegram ответил {response.status_code}")
        try:
            accepted = response.json().get("ok") is True
        except (ValueError, AttributeError):
            accepted = False
        if not accepted:
            raise NotifyFailed("Telegram не принял сообщение")


class DisabledNotifier(Notifier):
    """Telegram не настроен (dev и test): сообщение не отправляется."""

    async def send(self, text: str) -> None:
        log.warning("telegram_disabled")
