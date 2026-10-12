"""Сводка для главной страницы админки (только чтение)."""

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.dashboard.schemas import (
    DashboardResponse,
    NeedsMarkingSection,
    NewLeadsSection,
    PendingRequestsSection,
)
from app.leads import service as leads_service
from app.leads.models import LeadStatus
from app.lessons import requests_service
from app.lessons import service as lessons_service
from app.lessons.generation import local_midnight
from app.lessons.tutor_settings import get_timezone

LEADS_LIMIT = 5
REQUESTS_LIMIT = 5
NEEDS_MARKING_LIMIT = 10


async def get_dashboard(session: AsyncSession, *, now: datetime) -> DashboardResponse:
    tz = await get_timezone(session)
    today = now.astimezone(tz).date()
    day_start = local_midnight(today, tz)
    day_end = local_midnight(today + timedelta(days=1), tz)

    leads = await leads_service.list_leads(
        session, status=LeadStatus.NEW, q=None, limit=LEADS_LIMIT, offset=0
    )
    requests, requests_total = await requests_service.pending_summary(session, limit=REQUESTS_LIMIT)
    marking, marking_total = await lessons_service.list_needs_marking(
        session, now=now, limit=NEEDS_MARKING_LIMIT
    )
    day = await lessons_service.list_day_lessons(session, day_start=day_start, day_end=day_end)
    return DashboardResponse(
        new_leads=NewLeadsSection(items=leads.items, total=leads.total),
        pending_requests=PendingRequestsSection(items=requests, total=requests_total),
        needs_marking=NeedsMarkingSection(items=marking, total=marking_total),
        today=day,
        timezone=tz.key,
    )
