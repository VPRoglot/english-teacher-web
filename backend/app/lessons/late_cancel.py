"""Правило поздней отмены (план 6, уточнение 2)."""

from datetime import datetime, timedelta


def is_late_cancel(*, requested_at: datetime, starts_at: datetime, policy_hours: int) -> bool:
    """Отмена поздняя, если до начала меньше `policy_hours` часов на момент подачи запроса."""
    return starts_at - requested_at < timedelta(hours=policy_hours)
