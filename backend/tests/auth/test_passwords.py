import pytest

from app.auth.passwords import (
    hash_password,
    password_needs_rehash,
    validate_password,
    verify_password,
)
from app.core.errors import ValidationFailed


def test_hash_and_verify_cyrillic_password() -> None:
    h = hash_password("Пароль-123 !")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "Пароль-123 !") is True
    assert verify_password(h, "пароль-123 !") is False


def test_hashes_are_salted() -> None:
    assert hash_password("same-password") != hash_password("same-password")


def test_verify_garbage_hash_returns_false() -> None:
    assert verify_password("not-a-hash", "x") is False


def test_fresh_hash_does_not_need_rehash() -> None:
    assert password_needs_rehash(hash_password("secret-pass")) is False


def test_validate_password_too_short() -> None:
    with pytest.raises(ValidationFailed) as e:
        validate_password("1234567")
    assert e.value.code == "password_too_short"
    assert e.value.details == {"min_length": 8}
    validate_password("12345678")
    validate_password("123456", min_length=6)
