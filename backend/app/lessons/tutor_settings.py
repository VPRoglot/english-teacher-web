from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lessons.generation import active_series_ids_stmt, lock_series, shift_series_timezone
from app.lessons.models import TutorSettings
from app.lessons.schemas import TutorSettingsUpdate

LockMode = Literal["update", "share"]


async def get_tutor_settings(
    session: AsyncSession, *, lock: LockMode | None = None
) -> TutorSettings:
    """Единственная строка настроек: её создаёт миграция, без неё развёртывание сломано.

    `lock` берёт блокировку строки до конца транзакции и перечитывает актуальные значения:
    `update` — для смены настроек, `share` — для операций, которым нужен пояс, не меняющийся
    до коммита (создание и правка серий).
    """
    if lock is None:
        settings = await session.get(TutorSettings, 1)
    else:
        stmt = select(TutorSettings).where(TutorSettings.id == 1)
        stmt = stmt.with_for_update(read=lock == "share")
        settings = await session.scalar(stmt.execution_options(populate_existing=True))
    if settings is None:
        raise RuntimeError("В tutor_settings нет строки id=1: примените миграции")
    return settings


async def get_timezone(session: AsyncSession, *, lock: bool = False) -> ZoneInfo:
    """Пояс репетитора; `lock=True` — под `FOR SHARE`: смена пояса дождётся нашей транзакции."""
    settings = await get_tutor_settings(session, lock="share" if lock else None)
    return ZoneInfo(settings.timezone)


async def update_tutor_settings(
    session: AsyncSession, data: TutorSettingsUpdate, *, now: datetime
) -> TutorSettings:
    """Сохраняет настройки.

    Строка настроек читается `FOR UPDATE`: параллельное создание или правка серии держит её
    `FOR SHARE`, поэтому либо завершится до смены пояса и будет сдвинуто вместе с остальными
    сериями, либо дождётся её. Порядок блокировок везде один: настройки → серии → занятия.

    При смене часового пояса будущие занятия активных серий (`scheduled`, без `is_detached`)
    сдвигаются на месте: они остаются в то же местное время, но уже в новом поясе, а их id и
    заметки сохраняются. Разовые, пробные, отмеченные и отсоединённые занятия сохраняют свой
    момент времени.
    """
    settings = await get_tutor_settings(session, lock="update")
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
