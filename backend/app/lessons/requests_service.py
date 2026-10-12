"""Запросы на перенос и отмену занятий."""

import uuid
from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lessons.models import ChangeRequest


async def lesson_ids_with_requests(
    session: AsyncSession, lesson_ids: Collection[uuid.UUID]
) -> set[uuid.UUID]:
    """Id занятий из `lesson_ids`, у которых есть запрос в любом статусе (одним запросом)."""
    if not lesson_ids:
        return set()
    stmt = select(ChangeRequest.lesson_id).where(ChangeRequest.lesson_id.in_(lesson_ids)).distinct()
    return set(await session.scalars(stmt))
