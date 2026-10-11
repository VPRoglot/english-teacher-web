from datetime import UTC, datetime
from typing import Any

from app.core.db import new_uuid7
from app.leads.models import ContactMethod, Lead, LeadStatus


def make_lead(**overrides: Any) -> Lead:
    """Заявка в памяти (без БД); `overrides` заменяют поля."""
    values: dict[str, Any] = {
        "id": new_uuid7(),
        "parent_name": "Анна",
        "child_name": "Маша",
        "child_age": 9,
        "phone": "+79991234567",
        "contact_method": ContactMethod.TELEGRAM,
        "messenger_handle": None,
        "goal": None,
        "preferred_time": None,
        "status": LeadStatus.NEW,
        "consent_at": datetime.now(UTC),
    }
    return Lead(**{**values, **overrides})
