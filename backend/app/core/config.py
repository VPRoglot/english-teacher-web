from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
