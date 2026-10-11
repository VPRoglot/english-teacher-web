from typing import Annotated, Protocol

import structlog
from aiobotocore.config import AioConfig
from aiobotocore.session import get_session
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Depends, Request

from app.core.config import Settings
from app.site_content.errors import StorageUnavailable

log = structlog.get_logger("app.media")


class MediaStorage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...


class S3MediaStorage(MediaStorage):
    """Хранилище в S3-совместимом сервисе (MinIO в разработке).

    Клиент создаётся на каждый вызов: загрузки редкие, а долгоживущее соединение с хранилищем
    лишний ресурс, которым надо управлять в lifespan.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._session = get_session()

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        settings = self._settings
        config = AioConfig(
            s3={"addressing_style": settings.s3_addressing_style},
            connect_timeout=5,
            read_timeout=30,
            retries={"max_attempts": 2},
        )
        try:
            async with self._session.create_client(
                "s3",
                region_name=settings.s3_region,
                endpoint_url=settings.s3_endpoint_url,
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
                config=config,
            ) as client:
                await client.put_object(
                    Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type
                )
        except (BotoCoreError, ClientError) as exc:
            log.warning("media_put_failed", key=key, error=type(exc).__name__)
            raise StorageUnavailable from exc


def get_media_storage(request: Request) -> MediaStorage:
    storage: MediaStorage = request.app.state.media_storage
    return storage


MediaStorageDep = Annotated[MediaStorage, Depends(get_media_storage)]
