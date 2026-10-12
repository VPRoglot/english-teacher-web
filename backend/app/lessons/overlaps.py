from collections.abc import Collection
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.families.models import Child
from app.leads.models import Lead
from app.lessons.models import Lesson, LessonStatus
from app.lessons.schemas import OverlapWarning

# Отменённые занятия время не занимают.
BUSY_STATUSES = (LessonStatus.SCHEDULED, LessonStatus.COMPLETED, LessonStatus.NO_SHOW)
MAX_WARNINGS = 20


async def find_overlaps(
    session: AsyncSession,
    *,
    starts_at: datetime,
    duration_min: int,
    tz: ZoneInfo,
    exclude_ids: Collection[UUID] = (),
) -> list[OverlapWarning]:
    """Занятия, пересекающиеся с окном `[starts_at, starts_at + duration_min)`.

    Касание границами не пересечение. Предупреждения информационные: занятия не блокируются.
    """
    window_end = starts_at + timedelta(minutes=duration_min)
    lesson_end = Lesson.starts_at + func.make_interval(0, 0, 0, 0, 0, Lesson.duration_min)
    stmt = (
        select(Lesson.id, Lesson.starts_at, Child.full_name, Lead.child_name)
        .outerjoin(Child, Child.id == Lesson.child_id)
        .outerjoin(Lead, Lead.id == Lesson.lead_id)
        .where(
            Lesson.status.in_(BUSY_STATUSES),
            Lesson.starts_at < window_end,
            lesson_end > starts_at,
        )
        .order_by(Lesson.starts_at, Lesson.id)
        .limit(MAX_WARNINGS)
    )
    if exclude_ids:
        stmt = stmt.where(Lesson.id.not_in(exclude_ids))

    warnings: list[OverlapWarning] = []
    for lesson_id, lesson_starts_at, child_name, lead_child_name in await session.execute(stmt):
        name = f"Пробное: {lead_child_name}" if lead_child_name is not None else child_name
        when = lesson_starts_at.astimezone(tz).strftime("%d.%m %H:%M")
        warnings.append(
            OverlapWarning(
                code="overlap",
                message=f"Пересекается с занятием «{name}» {when}",
                lesson_id=lesson_id,
                starts_at=lesson_starts_at,
            )
        )
    return warnings
