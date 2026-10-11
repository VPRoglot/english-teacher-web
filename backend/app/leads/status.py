from collections.abc import Mapping

from app.leads.models import LeadStatus

# Таблица переходов из спеки 3.2; converted — конечный статус.
TRANSITIONS: Mapping[LeadStatus, frozenset[LeadStatus]] = {
    LeadStatus.NEW: frozenset(
        {LeadStatus.CONTACTED, LeadStatus.TRIAL_SCHEDULED, LeadStatus.REJECTED}
    ),
    LeadStatus.CONTACTED: frozenset({LeadStatus.TRIAL_SCHEDULED, LeadStatus.REJECTED}),
    LeadStatus.TRIAL_SCHEDULED: frozenset(
        {LeadStatus.CONVERTED, LeadStatus.REJECTED, LeadStatus.CONTACTED}
    ),
    LeadStatus.REJECTED: frozenset({LeadStatus.CONTACTED}),
    LeadStatus.CONVERTED: frozenset(),
}

# Статусы, которые репетитор выставляет вручную через PATCH; остальные — побочный эффект
# назначения пробного (план 5) и конвертации.
MANUAL_TARGETS: frozenset[LeadStatus] = frozenset({LeadStatus.CONTACTED, LeadStatus.REJECTED})


def can_transition(current: LeadStatus, target: LeadStatus) -> bool:
    return target in TRANSITIONS[current]
