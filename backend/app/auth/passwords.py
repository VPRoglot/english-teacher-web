from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.errors import ValidationFailed

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


def validate_password(password: str, *, min_length: int = 8) -> None:
    if len(password) < min_length:
        raise ValidationFailed(
            f"Пароль должен быть не короче {min_length} символов",
            code="password_too_short",
            details={"min_length": min_length},
        )
