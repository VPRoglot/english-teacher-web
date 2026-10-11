from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")  # файлы .env — см. ENV_FILES

    app_env: Literal["dev", "test", "prod"] = "dev"
    database_url: str
    redis_url: str
    log_level: str = "INFO"
    log_json: bool = True

    @field_validator("database_url")
    @classmethod
    def _require_asyncpg(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL должен начинаться с postgresql+asyncpg://")
        return value

    @field_validator("redis_url")
    @classmethod
    def _require_redis_scheme(cls, value: str) -> str:
        if not value.startswith(("redis://", "rediss://")):
            raise ValueError("REDIS_URL должен начинаться с redis:// или rediss://")
        return value


# Корневой .env (общий с docker compose), затем .env текущей папки — он переопределяет первый.
# Для backend вне Docker (`just api`, cwd = backend/) localhost-хосты кладут в backend/.env.
# В контейнере корень — "/", файла /.env нет, настройки приходят из окружения.
ENV_FILES: tuple[Path, ...] = (Path(__file__).resolve().parents[3] / ".env", Path(".env"))


@lru_cache
def get_settings() -> Settings:
    return Settings(_env_file=ENV_FILES)
