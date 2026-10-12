from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.lessons.generation import active_series_ids_stmt, lock_series, shift_series_timezone
from app.lessons.models import TutorSettings
from app.lessons.schemas import TutorSettingsUpdate


async def get_tutor_settings(session: AsyncSession) -> TutorSettings:
    """Единственная строка настроек: её создаёт миграция, без неё развёртывание сломано."""
    settings = await session.get(TutorSettings, 1)
    if settings is None:
        raise RuntimeError("В tutor_settings нет строки id=1: примените миграции")
    return settings


async def get_timezone(session: AsyncSession) -> ZoneInfo:
    return ZoneInfo((await get_tutor_settings(session)).timezone)


async def update_tutor_settings(
    session: AsyncSession, data: TutorSettingsUpdate, *, now: datetime
) -> TutorSettings:
    """Сохраняет настройки.

    При смене часового пояса будущие занятия активных серий (`scheduled`, без `is_detached`)
    сдвигаются на месте: они остаются в то же местное время, но уже в новом поясе, а их id и
    заметки сохраняются. Разовые, пробные, отмеченные и отсоединённые занятия сохраняют свой
    момент времени.
    """
    settings = await get_tutor_settings(session)
    old_tz = ZoneInfo(settings.timezone)
    settings.timezone = data.timezone
    settings.cancel_policy_hours = data.cancel_policy_hours
    await session.flush()
    new_tz = ZoneInfo(data.timezone)
    if new_tz.key != old_tz.key:
        today = now.astimezone(new_tz).date()
        for series_id in list(await session.scalars(active_series_ids_stmt(today))):
            series = await lock_series(session, series_id)
            if series is None or series.archived_at is not None:
                continue
            await shift_series_timezone(session, series, old_tz=old_tz, new_tz=new_tz, now=now)
    return settings
