import hashlib
import secrets
from datetime import timedelta

INVITATION_TTL = timedelta(days=7)
RESET_TTL = timedelta(hours=24)


def sha256_hex(token: str) -> str:
    """Хэш токена для хранения: сами токены в БД и Redis не лежат."""
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> tuple[str, str]:
    """Одноразовый токен для ссылки и его хэш — в БД попадает только хэш."""
    token = secrets.token_urlsafe(32)
    return token, sha256_hex(token)
