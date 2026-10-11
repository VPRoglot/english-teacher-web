import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.site_content.models import BlockKey, Media, SiteBlock
from app.site_content.schemas import BLOCK_SCHEMAS


async def test_migration_seeds_valid_stub_for_every_block(db_session: AsyncSession) -> None:
    rows = (await db_session.execute(select(SiteBlock))).scalars().all()
    assert {r.key for r in rows} == {k.value for k in BlockKey}
    for row in rows:
        BLOCK_SCHEMAS[BlockKey(row.key)].model_validate(row.data)


async def test_unknown_block_key_is_rejected_by_db(db_session: AsyncSession) -> None:
    db_session.add(SiteBlock(key="pricing", data={}))
    with pytest.raises(IntegrityError, match="ck_site_blocks_key_known"):
        await db_session.flush()


async def test_media_s3_key_is_unique(db_session: AsyncSession) -> None:
    def media() -> Media:
        return Media(
            s3_key="site/a.jpg", content_type="image/jpeg", size_bytes=1, width=1, height=1
        )

    db_session.add(media())
    await db_session.flush()
    db_session.add(media())
    with pytest.raises(IntegrityError, match="uq_media_s3_key"):
        await db_session.flush()
