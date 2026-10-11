import hashlib


def sha256_hex(token: str) -> str:
    """Хэш токена для хранения: сами токены в БД и Redis не лежат."""
    return hashlib.sha256(token.encode()).hexdigest()
