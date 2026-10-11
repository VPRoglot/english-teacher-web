from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.auth import router as auth_router
from app.core import csrf, health
from app.core.config import Settings, get_settings
from app.core.csrf import CsrfMiddleware
from app.core.db import create_db_engine, create_sessionmaker
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.redis import create_redis
from app.core.request_id import RequestIdMiddleware
from app.families import admin_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Ресурсы создаются без подключения: приложение стартует, даже если БД/Redis недоступны.
        app.state.engine = create_db_engine(settings)
        app.state.sessionmaker = create_sessionmaker(app.state.engine)
        app.state.redis = create_redis(settings)
        try:
            yield
        finally:
            await app.state.engine.dispose()
            await app.state.redis.aclose()

    app = FastAPI(
        title="English Tutor API",
        docs_url=None if settings.app_env == "prod" else "/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        generate_unique_id_function=lambda route: route.name,
        lifespan=lifespan,
    )
    app.state.settings = settings
    register_error_handlers(app)
    # Последний добавленный — внешний: request id остаётся самым внешним слоем.
    app.add_middleware(CsrfMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health.router, prefix="/api")
    app.include_router(csrf.router, prefix="/api")
    app.include_router(auth_router.router, prefix="/api")
    app.include_router(admin_router.router, prefix="/api")
    return app
