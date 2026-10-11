from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core import config
from app.core.config import Settings, get_settings
from tests.conftest import make_settings


def test_settings_require_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_env_files_are_repo_root_then_cwd() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    assert config.ENV_FILES == (repo_root / ".env", Path(".env"))


def test_get_settings_reads_root_env_and_cwd_env_overrides_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("DATABASE_URL", "REDIS_URL", "LOG_LEVEL", "REVALIDATE_SECRET"):
        monkeypatch.delenv(name, raising=False)
    root_env = tmp_path / "root.env"
    root_env.write_text(
        "DATABASE_URL=postgresql+asyncpg://u:p@postgres:5432/db\n"
        "REDIS_URL=redis://redis:6379/0\nLOG_LEVEL=WARNING\n"
        "REVALIDATE_SECRET=root-env-revalidate-secret\n",
        encoding="utf-8",
    )
    workdir = tmp_path / "backend"
    workdir.mkdir()
    (workdir / ".env").write_text(
        "DATABASE_URL=postgresql+asyncpg://u:p@localhost:5432/db\n", encoding="utf-8"
    )
    monkeypatch.chdir(workdir)
    monkeypatch.setattr(config, "ENV_FILES", (root_env, Path(".env")))
    get_settings.cache_clear()
    try:
        s = get_settings()
    finally:
        get_settings.cache_clear()
    assert s.database_url == "postgresql+asyncpg://u:p@localhost:5432/db"
    assert s.redis_url == "redis://redis:6379/0"
    assert s.log_level == "WARNING"


def test_session_settings_defaults() -> None:
    s = make_settings()
    assert s.session_cookie_secure is True
    assert s.public_base_url == "http://localhost:3000"
    assert s.revalidate_url == "http://localhost:3000/api/revalidate"


def test_public_base_url_trailing_slash_stripped() -> None:
    s = make_settings(public_base_url="https://x.ru/")
    assert s.public_base_url == "https://x.ru"


def test_settings_reject_sync_driver() -> None:
    with pytest.raises(ValidationError):
        make_settings(database_url="postgresql://u:p@h/db")


def test_revalidate_secret_is_required_and_long_enough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REVALIDATE_SECRET", raising=False)
    with pytest.raises(ValidationError, match="revalidate_secret"):
        Settings(
            _env_file=None, database_url="postgresql+asyncpg://u:p@h/db", redis_url="redis://h"
        )
    with pytest.raises(ValidationError, match="не короче 16 символов"):
        make_settings(revalidate_secret="short")
    s = make_settings(revalidate_secret="x" * 16)
    assert s.revalidate_secret.get_secret_value() == "x" * 16
