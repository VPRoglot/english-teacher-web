from functools import lru_cache
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_PLACEHOLDER = "change-me"


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
    # Необязательны в dev и test; в prod обязательны (см. `_require_prod_integrations`).
    smartcaptcha_server_key: SecretStr | None = None
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None
    # Доверенные адреса прокси для X-Forwarded-* (список через запятую или `*`).
    # Пусто — заголовки игнорируются; включать только за nginx, который перезаписывает XFF.
    forwarded_allow_ips: str = ""
    # Мониторинг: необязателен везде, включая prod. Без DSN Sentry отключён.
    sentry_dsn: SecretStr | None = None
    sentry_traces_sample_rate: float = Field(default=0.0, ge=0, le=1)
    # Версия сборки (тег образа) для Sentry release; в окружении — IMAGE_TAG.
    release: str | None = Field(default=None, validation_alias=AliasChoices("IMAGE_TAG", "release"))
    # Heartbeat-URL (healthchecks.io и т. п.): ежедневные задачи пингуют после успеха.
    heartbeat_materialize_url: SecretStr | None = None
    heartbeat_anonymize_url: SecretStr | None = None

    @field_validator(
        "smartcaptcha_server_key",
        "telegram_bot_token",
        "telegram_chat_id",
        "sentry_dsn",
        "heartbeat_materialize_url",
        "heartbeat_anonymize_url",
        mode="before",
    )
    @classmethod
    def _empty_means_absent(cls, value: object) -> object:
        # `KEY=` (или пробелы) в .env — то же, что закомментированная строка: интеграция выключена.
        if isinstance(value, str) and not value.strip():
            return None
        return value

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

    @model_validator(mode="after")
    def _require_prod_integrations(self) -> Self:
        # Пустая строка (`KEY=` в .env) считается отсутствием значения.
        if self.app_env == "prod" and not (
            self.smartcaptcha_server_key and self.telegram_bot_token and self.telegram_chat_id
        ):
            raise ValueError(
                "В production обязательны SMARTCAPTCHA_SERVER_KEY, "
                "TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID"
            )
        return self

    @model_validator(mode="after")
    def _require_prod_safety(self) -> Self:
        if self.app_env != "prod":
            return self
        host = urlparse(self.public_base_url).hostname
        if not self.public_base_url.startswith("https://") or host in _LOCAL_HOSTS:
            raise ValueError("PUBLIC_BASE_URL в production: только https и не localhost")
        if not self.session_cookie_secure:
            raise ValueError("SESSION_COOKIE_SECURE в production должен быть включён")
        for name, value in (
            ("REVALIDATE_SECRET", self.revalidate_secret.get_secret_value()),
            ("DATABASE_URL", self.database_url),
            ("S3_SECRET_KEY", self.s3_secret_key.get_secret_value()),
        ):
            if _PLACEHOLDER in value:
                raise ValueError(f"{name} в production не может содержать заглушку {_PLACEHOLDER}")
        return self


# Корневой .env (общий с docker compose), затем .env текущей папки — он переопределяет первый.
# Для backend вне Docker (`just api`, cwd = backend/) localhost-хосты кладут в backend/.env.
# В контейнере корень — "/", файла /.env нет, настройки приходят из окружения.
ENV_FILES: tuple[Path, ...] = (Path(__file__).resolve().parents[3] / ".env", Path(".env"))


@lru_cache
def get_settings() -> Settings:
    return Settings(_env_file=ENV_FILES)
