from datetime import UTC, datetime, timedelta

import pytest

from app.lessons.late_cancel import is_late_cancel

START = datetime(2026, 10, 20, 15, tzinfo=UTC)


@pytest.mark.parametrize(
    ("before", "policy", "late"),
    [
        (timedelta(hours=24, minutes=1), 24, False),
        (timedelta(hours=23, minutes=59), 24, True),
        (timedelta(hours=24), 24, False),
        (timedelta(minutes=5), 0, False),
        (timedelta(hours=2), 12, True),
    ],
)
def test_is_late_cancel(before: timedelta, policy: int, late: bool) -> None:
    assert is_late_cancel(requested_at=START - before, starts_at=START, policy_hours=policy) is late
