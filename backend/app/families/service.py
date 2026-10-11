import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.families.models import Child, Family, ParentProfile


async def get_parent_profile(session: AsyncSession, user_id: uuid.UUID) -> ParentProfile | None:
    return await session.get(ParentProfile, user_id)


async def get_family(session: AsyncSession, family_id: uuid.UUID) -> Family | None:
    return await session.get(Family, family_id)


async def list_active_children(session: AsyncSession, family_id: uuid.UUID) -> list[Child]:
    result = await session.scalars(
        select(Child)
        .where(Child.family_id == family_id, Child.archived_at.is_(None))
        .order_by(Child.full_name)
    )
    return list(result)


async def get_child_by_user(session: AsyncSession, user_id: uuid.UUID) -> Child | None:
    return await session.scalar(select(Child).where(Child.user_id == user_id))
