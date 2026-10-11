import pytest

from app.auth.passwords import (
    CHILD_PASSWORD_MIN_LENGTH,
    COMMON_PASSWORDS,
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
    validate_password("x7Kp-2mQ")
    validate_password("x7Kp-2", min_length=6)


@pytest.mark.parametrize("pw", ["12345678", "Qwerty123", "password", "йцукен123", "11111111"])
def test_common_passwords_rejected(pw: str) -> None:
    with pytest.raises(ValidationFailed) as e:
        validate_password(pw)
    assert e.value.code == "password_too_common"


def test_too_long_password_rejected() -> None:
    with pytest.raises(ValidationFailed) as e:
        validate_password("x" * 129)
    assert e.value.code == "password_too_long"
    assert e.value.details == {"max_length": 128}


def test_child_min_length() -> None:
    validate_password("Ab3$xy", min_length=CHILD_PASSWORD_MIN_LENGTH)


def test_common_list_is_substantial() -> None:
    assert len(COMMON_PASSWORDS) >= 150
    assert all(len(p) >= 6 for p in COMMON_PASSWORDS)


@pytest.mark.parametrize(
    "pw", ["secret-pass", "Пароль-123 !", "Correct-Horse-7", "New-Strong-9", "Strong-pass-1"]
)
def test_passwords_used_by_other_tests_are_not_common(pw: str) -> None:
    assert pw.lower() not in COMMON_PASSWORDS
    validate_password(pw)
