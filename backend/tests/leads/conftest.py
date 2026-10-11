from typing import Any

import pytest
from fastapi import FastAPI

from app.leads.captcha import get_captcha_verifier


class FakeCaptcha:
    """Проверка капчи для API-тестов: запоминает вызовы и возвращает заданный результат."""

    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.calls: list[tuple[str | None, str | None]] = []

    async def verify(self, token: str | None, ip: str | None) -> bool:
        self.calls.append((token, ip))
        return self.result


@pytest.fixture
def captcha(app: FastAPI) -> FakeCaptcha:
    fake = FakeCaptcha(True)
    app.dependency_overrides[get_captcha_verifier] = lambda: fake
    return fake


def valid_lead(**overrides: Any) -> dict[str, Any]:
    """Тело валидной публичной заявки; `overrides` заменяют или добавляют поля."""
    body: dict[str, Any] = {
        "parent_name": "Анна",
        "child_name": "Маша",
        "child_age": 9,
        "phone": "+7 999 123-45-67",
        "contact_method": "telegram",
        "consent": True,
        "captcha_token": "token",
    }
    return {**body, **overrides}
