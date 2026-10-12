from pydantic import BaseModel

from app.leads.schemas import LeadListItem
from app.lessons.schemas import AdminLessonItem, ChangeRequestAdminItem


class NewLeadsSection(BaseModel):
    items: list[LeadListItem]
    total: int


class PendingRequestsSection(BaseModel):
    items: list[ChangeRequestAdminItem]
    total: int


class NeedsMarkingSection(BaseModel):
    items: list[AdminLessonItem]
    total: int


class DashboardResponse(BaseModel):
    new_leads: NewLeadsSection
    pending_requests: PendingRequestsSection
    needs_marking: NeedsMarkingSection
    today: list[AdminLessonItem]
    timezone: str
