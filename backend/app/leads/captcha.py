from typing import Annotated, Protocol

import httpx
import structlog
from fastapi import Depends, Request

from app.core.errors import AppError

log = structlog.get_logger("app.leads")

VALIDATE_URL = "https://smartcaptcha.yandexcloud.net/validate"
_TIMEOUT_SECONDS = 3.0


class CaptchaFailed(AppError):  # noqa: N818 (как NotFound и др.: имя без суффикса Error)
    status_code = 400
    code = "captcha_failed"
    message = "Не удалось подтвердить, что вы не робот. Обновите страницу и попробуйте ещё раз"


class CaptchaVerifier(Protocol):
    async def verify(self, token: str | None, ip: str | None) -> bool: ...


class DisabledCaptchaVerifier:
    """Капча не настроена (dev, test): пропускает всех."""

    async def verify(self, token: str | None, ip: str | None) -> bool:
        return True


class YandexCaptchaVerifier:
    """Проверка токена Yandex SmartCaptcha.

    Fail-open (рекомендация Яндекса): недоступность сервиса капчи не должна блокировать
    заявки. Защиту при этом обеспечивают honeypot и rate limit.
    """

    def __init__(self, client: httpx.AsyncClient, server_key: str) -> None:
        self._client = client
        self._server_key = server_key

    async def verify(self, token: str | None, ip: str | None) -> bool:
        if not token:
            return False
        form = {"secret": self._server_key, "token": token}
        if ip:
            form["ip"] = ip
        try:
            response = await self._client.post(VALIDATE_URL, data=form, timeout=_TIMEOUT_SECONDS)
            if response.status_code != 200:
                log.warning("captcha_unavailable", status_code=response.status_code)
                return True
            body = response.json()
        except (httpx.HTTPError, ValueError):
            log.warning("captcha_unavailable", exc_info=True)
            return True
        return isinstance(body, dict) and body.get("status") == "ok"


def get_captcha_verifier(request: Request) -> CaptchaVerifier:
    verifier: CaptchaVerifier = request.app.state.captcha
    return verifier


CaptchaDep = Annotated[CaptchaVerifier, Depends(get_captcha_verifier)]
