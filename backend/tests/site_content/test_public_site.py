from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import new_uuid7
from app.site_content import service as site_service
from app.site_content.models import BlockKey, Media
from app.site_content.schemas import HeroBlock


async def test_public_site_returns_seeded_stubs_without_auth(client: AsyncClient) -> None:
    r = await client.get("/api/public/site")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"hero", "about", "services", "reviews", "faq", "contacts"}
    assert body["hero"]["cta_text"] == "Записаться на пробное"
    assert body["hero"]["photo"] is None
    assert body["reviews"] == {"items": []}


async def test_public_site_resolves_photo(client: AsyncClient, db_session: AsyncSession) -> None:
    media = Media(
        id=new_uuid7(),
        s3_key="site/a.jpg",
        content_type="image/jpeg",
        size_bytes=10,
        width=800,
        height=600,
    )
    db_session.add(media)
    await db_session.flush()
    hero = HeroBlock(
        name="Анна",
        title="Заголовок",
        subtitle="Подзаголовок",
        photo_media_id=media.id,
        cta_text="Записаться",
    )
    await site_service.save_block(db_session, BlockKey.HERO, hero)

    hero_public = (await client.get("/api/public/site")).json()["hero"]
    assert hero_public["photo"] == {"url": "/media/site/a.jpg", "width": 800, "height": 600}


async def test_public_site_hides_photo_whose_media_row_is_gone(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await db_session.execute(
        text(
            "UPDATE site_blocks SET data = jsonb_set(data, '{photo_media_id}', "
            "to_jsonb(CAST(:id AS text))) WHERE key = 'hero'"
        ),
        {"id": str(new_uuid7())},
    )
    r = await client.get("/api/public/site")
    assert r.status_code == 200
    assert r.json()["hero"]["photo"] is None
