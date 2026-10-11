import uuid
from typing import NamedTuple

import structlog
from anyio import to_thread
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import new_uuid7
from app.core.errors import ValidationFailed
from app.core.tasks import TaskQueue
from app.site_content.images import process_image
from app.site_content.models import BlockKey, Media, SiteBlock
from app.site_content.schemas import (
    AboutBlock,
    AboutPublic,
    ContactsBlock,
    FaqBlock,
    HeroBlock,
    HeroPublic,
    MediaOut,
    MediaRef,
    PublicSite,
    ReviewPublic,
    ReviewsBlock,
    ReviewsPublic,
    ServicesBlock,
    SiteBlocksAdmin,
    media_url,
    referenced_media_ids,
)
from app.site_content.storage import MediaStorage
from app.site_content.tasks import REVALIDATE_SITE_TASK

log = structlog.get_logger("app.site_content")


async def upload_media(
    session: AsyncSession, storage: MediaStorage, settings: Settings, data: bytes
) -> MediaOut:
    """Проверяет и пересохраняет картинку, кладёт её в хранилище и записывает строку `media`.

    Сначала хранилище, потом БД: если упадёт вставка, в бакете останется объект-сирота —
    безвредно. Обратный порядок оставил бы в БД ссылку на несуществующий файл.
    """
    image = await to_thread.run_sync(process_image, data)
    media = Media(
        id=new_uuid7(),
        s3_key=f"site/{new_uuid7()}.{image.extension}",
        content_type=image.content_type,
        size_bytes=len(image.data),
        width=image.width,
        height=image.height,
    )
    await storage.put(media.s3_key, image.data, image.content_type)
    session.add(media)
    await session.flush()
    return _media_out(settings, media)


class _Blocks(NamedTuple):
    hero: HeroBlock
    about: AboutBlock
    services: ServicesBlock
    reviews: ReviewsBlock
    faq: FaqBlock
    contacts: ContactsBlock

    def media_ids(self) -> list[uuid.UUID]:
        """Id всех упомянутых фото в порядке появления, без повторов."""
        return list(
            dict.fromkeys(media_id for block in self for _, media_id in referenced_media_ids(block))
        )


async def _load_blocks(session: AsyncSession) -> _Blocks:
    rows = {row.key: row.data for row in (await session.execute(select(SiteBlock))).scalars()}
    for key in BlockKey:
        if key.value not in rows:
            # Строки создаёт миграция: их отсутствие — ошибка развёртывания, а не запроса.
            raise RuntimeError(f"В site_blocks нет строки блока {key.value!r}")
    return _Blocks(
        hero=HeroBlock.model_validate(rows[BlockKey.HERO]),
        about=AboutBlock.model_validate(rows[BlockKey.ABOUT]),
        services=ServicesBlock.model_validate(rows[BlockKey.SERVICES]),
        reviews=ReviewsBlock.model_validate(rows[BlockKey.REVIEWS]),
        faq=FaqBlock.model_validate(rows[BlockKey.FAQ]),
        contacts=ContactsBlock.model_validate(rows[BlockKey.CONTACTS]),
    )


async def _load_media(session: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, Media]:
    if not ids:
        return {}
    rows = (await session.execute(select(Media).where(Media.id.in_(ids)))).scalars()
    return {media.id: media for media in rows}


def _media_out(settings: Settings, media: Media) -> MediaOut:
    return MediaOut(
        id=media.id,
        url=media_url(settings, media.s3_key),
        content_type=media.content_type,
        size_bytes=media.size_bytes,
        width=media.width,
        height=media.height,
    )


def _media_ref(
    settings: Settings, media_by_id: dict[uuid.UUID, Media], media_id: uuid.UUID | None
) -> MediaRef | None:
    media = media_by_id.get(media_id) if media_id is not None else None
    if media is None:
        return None  # строки media нет — показываем блок без фото, а не с битой картинкой
    return MediaRef(url=media_url(settings, media.s3_key), width=media.width, height=media.height)


async def get_site_blocks(session: AsyncSession, settings: Settings) -> SiteBlocksAdmin:
    blocks = await _load_blocks(session)
    ids = blocks.media_ids()
    media_by_id = await _load_media(session, ids)
    return SiteBlocksAdmin(
        hero=blocks.hero,
        about=blocks.about,
        services=blocks.services,
        reviews=blocks.reviews,
        faq=blocks.faq,
        contacts=blocks.contacts,
        media=[_media_out(settings, media_by_id[i]) for i in ids if i in media_by_id],
    )


async def save_block(session: AsyncSession, key: BlockKey, block: BaseModel) -> None:
    """Проверяет, что все фото блока существуют, и записывает блок (upsert по ключу)."""
    references = referenced_media_ids(block)
    if references:
        wanted = {media_id for _, media_id in references}
        found = set((await session.execute(select(Media.id).where(Media.id.in_(wanted)))).scalars())
        missing = [loc for loc, media_id in references if media_id not in found]
        if missing:
            raise ValidationFailed(
                "Фото не найдено — загрузите его заново",
                details={
                    "fields": [
                        {
                            "loc": ["body", *loc],
                            "message": "Фото не найдено",
                            "type": "media_not_found",
                        }
                        for loc in missing
                    ]
                },
            )
    statement = insert(SiteBlock).values(key=key.value, data=block.model_dump(mode="json"))
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[SiteBlock.key],
            set_={"data": statement.excluded.data, "updated_at": func.now()},
        )
    )


async def get_public_site(session: AsyncSession, settings: Settings) -> PublicSite:
    blocks = await _load_blocks(session)
    media_by_id = await _load_media(session, blocks.media_ids())
    return PublicSite(
        hero=HeroPublic(
            name=blocks.hero.name,
            title=blocks.hero.title,
            subtitle=blocks.hero.subtitle,
            photo=_media_ref(settings, media_by_id, blocks.hero.photo_media_id),
            cta_text=blocks.hero.cta_text,
        ),
        about=AboutPublic(
            text=blocks.about.text,
            photo=_media_ref(settings, media_by_id, blocks.about.photo_media_id),
            credentials=blocks.about.credentials,
        ),
        services=blocks.services,
        reviews=ReviewsPublic(
            items=[
                ReviewPublic(
                    author=item.author,
                    text=item.text,
                    child_age=item.child_age,
                    photo=_media_ref(settings, media_by_id, item.photo_media_id),
                )
                for item in blocks.reviews.items
            ]
        ),
        faq=blocks.faq,
        contacts=blocks.contacts,
    )


async def request_site_revalidation(queue: TaskQueue) -> None:
    """Просит worker сбросить кеш лендинга.

    Сбой очереди не должен ронять сохранение: блок уже записан, а устаревший кеш
    обновится при следующем сохранении.
    """
    try:
        await queue.enqueue(REVALIDATE_SITE_TASK)
    except Exception:
        log.warning("site_revalidation_enqueue_failed", exc_info=True)
