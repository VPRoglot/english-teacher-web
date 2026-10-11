from anyio import to_thread
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import new_uuid7
from app.site_content.images import process_image
from app.site_content.models import Media
from app.site_content.schemas import MediaOut, media_url
from app.site_content.storage import MediaStorage


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
    return MediaOut(
        id=media.id,
        url=media_url(settings, media.s3_key),
        content_type=media.content_type,
        size_bytes=media.size_bytes,
        width=media.width,
        height=media.height,
    )
