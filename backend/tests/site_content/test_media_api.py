import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from minio import Minio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.site_content.errors import StorageUnavailable
from app.site_content.images import MAX_UPLOAD_BYTES
from app.site_content.models import Media
from app.site_content.schemas import media_url
from app.site_content.storage import S3MediaStorage, get_media_storage
from tests.conftest import MINIO_BUCKET, make_settings
from tests.site_content.conftest import make_image


async def _media_count(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(Media))).scalar_one()


async def test_upload_stores_processed_file_and_row(
    tutor_client: AsyncClient, minio_client: Minio, db_session: AsyncSession
) -> None:
    r = await tutor_client.post(
        "/api/admin/media",
        files={"file": ("photo.png", make_image("JPEG", (800, 600)), "image/png")},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["url"].startswith("/media/site/")
    assert body["url"].endswith(".jpg")
    assert (body["width"], body["height"], body["content_type"]) == (800, 600, "image/jpeg")
    key = body["url"].removeprefix("/media/")
    stat = minio_client.stat_object(MINIO_BUCKET, key)
    assert stat.content_type == "image/jpeg"
    assert stat.size == body["size_bytes"]
    media = await db_session.get(Media, uuid.UUID(body["id"]))
    assert media is not None
    assert media.s3_key == key


async def test_upload_over_5_mb_is_413_and_nothing_stored(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    r = await tutor_client.post(
        "/api/admin/media",
        files={"file": ("big.jpg", b"\xff" * (MAX_UPLOAD_BYTES + 1), "image/jpeg")},
    )
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "file_too_large"
    assert await _media_count(db_session) == 0


async def test_upload_decompression_bomb_is_413_and_nothing_stored(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    bomb = make_image("PNG", (7000, 7000), mode="1")
    r = await tutor_client.post("/api/admin/media", files={"file": ("bomb.png", bomb, "image/png")})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "file_too_large"
    assert await _media_count(db_session) == 0


async def test_upload_fake_jpeg_is_415(tutor_client: AsyncClient, db_session: AsyncSession) -> None:
    r = await tutor_client.post(
        "/api/admin/media", files={"file": ("photo.jpg", b"not an image", "image/jpeg")}
    )
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "unsupported_media_type"
    assert await _media_count(db_session) == 0


async def test_upload_without_file_is_422(tutor_client: AsyncClient) -> None:
    r = await tutor_client.post("/api/admin/media")
    assert r.status_code == 422


async def test_upload_requires_login(client: AsyncClient) -> None:
    r = await client.post(
        "/api/admin/media", files={"file": ("a.jpg", make_image("JPEG", (10, 10)), "image/jpeg")}
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "not_authenticated"


async def test_upload_by_parent_is_404(parent_client: AsyncClient) -> None:
    r = await parent_client.post(
        "/api/admin/media", files={"file": ("a.jpg", make_image("JPEG", (10, 10)), "image/jpeg")}
    )
    assert r.status_code == 404


class _FailingStorage:
    async def put(self, key: str, data: bytes, content_type: str) -> None:
        raise StorageUnavailable


async def test_storage_failure_is_503_and_no_row(
    app: FastAPI, tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    app.dependency_overrides[get_media_storage] = _FailingStorage
    r = await tutor_client.post(
        "/api/admin/media",
        files={"file": ("a.jpg", make_image("JPEG", (10, 10)), "image/jpeg")},
    )
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "storage_unavailable"
    assert await _media_count(db_session) == 0


async def test_s3_storage_wraps_connection_errors(settings: Settings) -> None:
    storage = S3MediaStorage(settings.model_copy(update={"s3_endpoint_url": "http://127.0.0.1:1"}))
    with pytest.raises(StorageUnavailable):
        await storage.put("site/x.jpg", b"x", "image/jpeg")


async def test_s3_storage_wraps_client_errors(settings: Settings) -> None:
    # несуществующий бакет → ClientError (NoSuchBucket)
    storage = S3MediaStorage(settings.model_copy(update={"s3_bucket": "no-such-bucket"}))
    with pytest.raises(StorageUnavailable):
        await storage.put("site/x.jpg", b"x", "image/jpeg")


@pytest.mark.parametrize(
    ("base", "expected"),
    [
        ("/media", "/media/site/a.jpg"),
        ("/media/", "/media/site/a.jpg"),
        ("https://cdn.example.com/m", "https://cdn.example.com/m/site/a.jpg"),
    ],
)
def test_media_url_joins_base_and_key(base: str, expected: str) -> None:
    settings = make_settings(media_public_base_url=base)
    assert media_url(settings, "site/a.jpg") == expected
