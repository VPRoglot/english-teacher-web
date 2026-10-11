from typing import Any

import pytest
import structlog
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import new_uuid7
from app.core.tasks import get_task_queue
from app.site_content.models import Media, SiteBlock
from app.site_content.schemas import MediaOut
from tests.conftest import FakeTaskQueue

HERO = {
    "name": "  Анна Смирнова ",
    "title": "Английский с удовольствием",
    "subtitle": "Онлайн",
    "photo_media_id": None,
    "cta_text": "Записаться",
}


async def _add_media(session: AsyncSession, key: str = "site/a.jpg") -> Media:
    media = Media(
        id=new_uuid7(), s3_key=key, content_type="image/jpeg", size_bytes=10, width=800, height=600
    )
    session.add(media)
    await session.flush()
    return media


async def test_put_hero_saves_normalized_block_and_requests_revalidation(
    tutor_client: AsyncClient, task_queue: FakeTaskQueue
) -> None:
    r = await tutor_client.put("/api/admin/site-blocks/hero", json=HERO)
    assert r.status_code == 200
    assert r.json()["name"] == "Анна Смирнова"
    got = await tutor_client.get("/api/admin/site-blocks")
    assert got.json()["hero"]["name"] == "Анна Смирнова"
    assert task_queue.calls == [("site_content.revalidate_site", {})]


@pytest.mark.parametrize(
    ("key", "body"),
    [
        ("about", {"text": "Обо мне", "photo_media_id": None, "credentials": ["CELTA"]}),
        (
            "services",
            {
                "items": [
                    {
                        "title": "Урок",
                        "description": "",
                        "duration_min": 60,
                        "price_rub": 1500,
                        "format": "Онлайн",
                    }
                ]
            },
        ),
        (
            "reviews",
            {"items": [{"author": "А", "text": "Т", "child_age": 9, "photo_media_id": None}]},
        ),
        ("faq", {"items": [{"question": "Q", "answer": "A"}]}),
        (
            "contacts",
            {
                "telegram": "@anna_english",
                "whatsapp": None,
                "phone": None,
                "email": None,
                "working_hours_text": None,
            },
        ),
    ],
)
async def test_every_block_has_a_put_route(
    tutor_client: AsyncClient, task_queue: FakeTaskQueue, key: str, body: dict[str, Any]
) -> None:
    r = await tutor_client.put(f"/api/admin/site-blocks/{key}", json=body)
    assert r.status_code == 200
    assert (await tutor_client.get("/api/admin/site-blocks")).json()[key] == r.json()
    assert len(task_queue.calls) == 1


async def test_commit_happens_before_revalidation_is_enqueued(
    app: FastAPI,
    tutor_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    original_commit = db_session.commit

    async def commit() -> None:
        events.append("commit")
        await original_commit()

    class RecordingQueue:
        async def enqueue(self, task_name: str, /, **kwargs: Any) -> None:
            events.append("enqueue")

    monkeypatch.setattr(db_session, "commit", commit)
    app.dependency_overrides[get_task_queue] = lambda: RecordingQueue()

    r = await tutor_client.put("/api/admin/site-blocks/faq", json={"items": []})
    assert r.status_code == 200
    assert events[:2] == ["commit", "enqueue"]


async def test_block_is_saved_even_if_enqueue_fails(
    tutor_client: AsyncClient, task_queue: FakeTaskQueue
) -> None:
    task_queue.fail = True
    with structlog.testing.capture_logs() as logs:
        r = await tutor_client.put("/api/admin/site-blocks/hero", json=HERO)
    assert r.status_code == 200
    got = await tutor_client.get("/api/admin/site-blocks")
    assert got.json()["hero"]["name"] == "Анна Смирнова"
    failed = [e for e in logs if e["event"] == "site_revalidation_enqueue_failed"]
    assert len(failed) == 1
    assert failed[0]["log_level"] == "warning"


async def test_unknown_photo_is_422_with_field_path_and_nothing_saved(
    tutor_client: AsyncClient, task_queue: FakeTaskQueue
) -> None:
    r = await tutor_client.put(
        "/api/admin/site-blocks/reviews",
        json={
            "items": [
                {"author": "А", "text": "Т", "child_age": None, "photo_media_id": None},
                {"author": "Б", "text": "Т", "child_age": 9, "photo_media_id": str(new_uuid7())},
            ]
        },
    )
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    assert err["message"] == "Фото не найдено — загрузите его заново"
    assert err["details"]["fields"] == [
        {
            "loc": ["body", "items", 1, "photo_media_id"],
            "message": "Фото не найдено",
            "type": "media_not_found",
        }
    ]
    assert (await tutor_client.get("/api/admin/site-blocks")).json()["reviews"] == {"items": []}
    assert task_queue.calls == []


async def test_invalid_body_is_422_and_no_revalidation(
    tutor_client: AsyncClient, task_queue: FakeTaskQueue
) -> None:
    r = await tutor_client.put("/api/admin/site-blocks/hero", json={**HERO, "title": ""})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    assert err["details"]["fields"][0]["loc"] == ["body", "title"]
    assert task_queue.calls == []


async def test_admin_blocks_list_referenced_media(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    media = await _add_media(db_session)
    await _add_media(db_session, "site/unused.jpg")
    about = {"text": "Обо мне", "photo_media_id": str(media.id), "credentials": []}
    assert (await tutor_client.put("/api/admin/site-blocks/about", json=about)).status_code == 200

    body = (await tutor_client.get("/api/admin/site-blocks")).json()
    expected = MediaOut(
        id=media.id,
        url="/media/site/a.jpg",
        content_type="image/jpeg",
        size_bytes=10,
        width=800,
        height=600,
    )
    assert body["media"] == [expected.model_dump(mode="json")]


async def test_missing_block_row_is_a_deployment_error(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    await db_session.execute(delete(SiteBlock).where(SiteBlock.key == "faq"))
    r = await tutor_client.get("/api/admin/site-blocks")
    assert r.status_code == 500
    assert "faq" not in r.text  # детали развёртывания не утекают клиенту


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/api/admin/site-blocks"), ("PUT", "/api/admin/site-blocks/hero")],
)
async def test_site_blocks_require_login(client: AsyncClient, method: str, path: str) -> None:
    r = await client.request(method, path, json=HERO if method == "PUT" else None)
    assert r.status_code == 401


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/api/admin/site-blocks"), ("PUT", "/api/admin/site-blocks/hero")],
)
async def test_site_blocks_are_hidden_from_parents(
    parent_client: AsyncClient, method: str, path: str
) -> None:
    r = await parent_client.request(method, path, json=HERO if method == "PUT" else None)
    assert r.status_code == 404
