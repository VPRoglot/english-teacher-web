from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

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
    """Сохраняет настройки. `now` нужен перегенерации будущих занятий при смене пояса."""
    settings = await get_tutor_settings(session)
    settings.timezone = data.timezone
    settings.cancel_policy_hours = data.cancel_policy_hours
    await session.flush()
    return settings
