import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_require_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_reject_sync_driver() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="postgresql://u:p@h/db", redis_url="redis://h")
