from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.errors import ValidationFailed

PASSWORD_MIN_LENGTH = 8
CHILD_PASSWORD_MIN_LENGTH = 6
PASSWORD_MAX_LENGTH = 128


def _load_common_passwords() -> frozenset[str]:
    text = Path(__file__).with_name("common_passwords.txt").read_text(encoding="utf-8")
    lines = (line.strip() for line in text.splitlines())
    return frozenset(line.lower() for line in lines if line and not line.startswith("#"))


COMMON_PASSWORDS = _load_common_passwords()

_hasher = PasswordHasher()  # argon2id с рекомендованными параметрами


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def validate_password(password: str, *, min_length: int = PASSWORD_MIN_LENGTH) -> None:
    if len(password) < min_length:
        raise ValidationFailed(
            f"Пароль должен быть не короче {min_length} символов",
            code="password_too_short",
            details={"min_length": min_length},
        )
    if len(password) > PASSWORD_MAX_LENGTH:
        raise ValidationFailed(
            f"Пароль должен быть не длиннее {PASSWORD_MAX_LENGTH} символов",
            code="password_too_long",
            details={"max_length": PASSWORD_MAX_LENGTH},
        )
    if password.lower() in COMMON_PASSWORDS:
        raise ValidationFailed(
            "Этот пароль слишком распространён — выберите другой", code="password_too_common"
        )
