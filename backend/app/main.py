import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
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
from app.core.tasks import BrokerTaskQueue, create_broker
from app.families import admin_router, cabinet_router
from app.site_content import admin_router as site_admin_router
from app.site_content import public_router as site_public_router
from app.site_content.storage import S3MediaStorage
from app.site_content.upload_limit import UploadLimitMiddleware

log = structlog.get_logger("app.main")
_BROKER_STARTUP_TIMEOUT = 5  # секунд


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Ресурсы создаются без подключения: приложение стартует, даже если БД/Redis недоступны.
        app.state.engine = create_db_engine(settings)
        app.state.sessionmaker = create_sessionmaker(app.state.engine)
        app.state.redis = create_redis(settings)
        app.state.broker = broker = create_broker(settings)
        app.state.task_queue = BrokerTaskQueue(
            broker, timeout_seconds=settings.task_enqueue_timeout_seconds
        )
        app.state.media_storage = S3MediaStorage(settings)  # без сети: клиент создаётся на запрос
        try:
            # startup() брокера идёт в Redis (создаёт consumer group): если Redis недоступен,
            # приложение всё равно стартует, а постановка задачи упадёт позже и обработается там.
            try:
                async with asyncio.timeout(_BROKER_STARTUP_TIMEOUT):
                    await broker.startup()
            except Exception:
                log.warning("broker_startup_failed", exc_info=True)
            yield
        finally:
            await broker.shutdown()
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
    app.add_middleware(UploadLimitMiddleware)  # снаружи CSRF и авторизации
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health.router, prefix="/api")
    app.include_router(csrf.router, prefix="/api")
    app.include_router(auth_router.router, prefix="/api")
    app.include_router(admin_router.router, prefix="/api")
    app.include_router(cabinet_router.router, prefix="/api")
    app.include_router(site_admin_router.router, prefix="/api")
    app.include_router(site_public_router.router, prefix="/api")
    return app
