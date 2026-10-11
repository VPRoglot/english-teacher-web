from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")  # файлы .env — см. ENV_FILES

    app_env: Literal["dev", "test", "prod"] = "dev"
    database_url: str
    redis_url: str
    # Потолок постановки задачи в очередь: зависший Redis не должен вешать ответ API.
    task_enqueue_timeout_seconds: float = 2.0
    log_level: str = "INFO"
    log_json: bool = True
    session_cookie_secure: bool = True
    public_base_url: str = "http://localhost:3000"
    revalidate_url: str = "http://localhost:3000/api/revalidate"
    revalidate_secret: SecretStr
    # S3-совместимое хранилище медиа (MinIO в разработке). endpoint None — настоящий AWS S3.
    s3_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_bucket: str
    s3_access_key: str
    s3_secret_key: SecretStr
    s3_addressing_style: Literal["path", "virtual"] = "path"
    # Префикс публичных URL медиа: `{media_public_base_url}/{s3_key}`.
    media_public_base_url: str = "/media"

    @field_validator("revalidate_secret")
    @classmethod
    def _require_long_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 16:
            raise ValueError("REVALIDATE_SECRET: не короче 16 символов")
        return value

    @field_validator("public_base_url", "media_public_base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

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
