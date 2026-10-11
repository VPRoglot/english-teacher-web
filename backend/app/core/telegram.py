import re

_PREFIXES = ("https://t.me/", "http://t.me/", "t.me/", "@")

TELEGRAM_HANDLE_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")


def strip_telegram_handle(value: str) -> str:
    """Убирает ссылку `t.me/` и ведущий `@`: `@anna`, `t.me/anna`, `https://t.me/anna` → `anna`."""
    username = value.strip()
    for prefix in _PREFIXES:
        if username.lower().startswith(prefix):
            username = username[len(prefix) :]
    return username.strip()
