from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.lessons.recurrence import InvalidRule, normalize_rule, occurrences

MSK, BERLIN = ZoneInfo("Europe/Moscow"), ZoneInfo("Europe/Berlin")


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("FREQ=WEEKLY;BYDAY=FR,TU", "FREQ=WEEKLY;BYDAY=TU,FR"),
        ("freq=weekly; interval=2; byday=mo", "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO"),
        ("FREQ=WEEKLY;INTERVAL=1;BYDAY=SU", "FREQ=WEEKLY;BYDAY=SU"),
        ("  FREQ = WEEKLY ; BYDAY = su, mo , we ", "FREQ=WEEKLY;BYDAY=MO,WE,SU"),
        ("BYDAY=TH;INTERVAL=4;FREQ=WEEKLY", "FREQ=WEEKLY;INTERVAL=4;BYDAY=TH"),
    ],
)
def test_normalize_rule(raw: str, canonical: str) -> None:
    assert normalize_rule(raw) == canonical


@pytest.mark.parametrize(
    "raw",
    [
        "FREQ=DAILY;BYDAY=MO",
        "FREQ=WEEKLY",
        "FREQ=WEEKLY;BYDAY=XX",
        "FREQ=WEEKLY;BYDAY=MO,MO",
        "FREQ=WEEKLY;BYDAY=MO;INTERVAL=5",
        "FREQ=WEEKLY;BYDAY=MO;INTERVAL=0",
        "FREQ=WEEKLY;BYDAY=MO;INTERVAL=x",
        "FREQ=WEEKLY;BYDAY=MO;COUNT=3",
        "FREQ=WEEKLY;BYDAY=MO;UNTIL=20270101T000000Z",
        "DTSTART:20261001T100000\nRRULE:FREQ=WEEKLY;BYDAY=MO",
        "FREQ=WEEKLY;BYDAY=1MO",
        "FREQ=WEEKLY;BYDAY=",
        "FREQ=WEEKLY;BYDAY=MO;",
        "FREQ=WEEKLY;FREQ=WEEKLY;BYDAY=MO",
        "FREQ=WEEKLY;BYDAY=MO;INTERVAL=1;INTERVAL=2",
        "",
    ],
)
def test_normalize_rule_rejects(raw: str) -> None:
    with pytest.raises(InvalidRule) as error:
        normalize_rule(raw)
    assert str(error.value)  # русское сообщение, не пустое


def test_weekly_moscow_converts_each_date_to_utc() -> None:
    got = occurrences(
        "FREQ=WEEKLY;BYDAY=TU,FR",
        starts_on=date(2026, 10, 13),
        ends_on=None,
        local_time=time(18, 0),
        tz=MSK,
        first_day=date(2026, 10, 13),
        last_day=date(2026, 10, 20),
    )
    assert got == [
        datetime(2026, 10, 13, 15, tzinfo=UTC),
        datetime(2026, 10, 16, 15, tzinfo=UTC),
        datetime(2026, 10, 20, 15, tzinfo=UTC),
    ]


def test_dst_keeps_local_time() -> None:
    got = occurrences(
        "FREQ=WEEKLY;BYDAY=TU",
        starts_on=date(2026, 3, 17),
        ends_on=None,
        local_time=time(10, 0),
        tz=BERLIN,
        first_day=date(2026, 3, 17),
        last_day=date(2026, 3, 31),
    )
    # 17.03 и 24.03 — CET (UTC+1), 31.03 — CEST (UTC+2)
    assert [d.hour for d in got] == [9, 9, 8]
    assert all(d.tzinfo is UTC for d in got)


def test_nonexistent_local_time_moves_forward() -> None:
    # 2026-03-29 02:30 в Берлине не существует (02:00 → 03:00): получается 03:30 CEST = 01:30 UTC.
    got = occurrences(
        "FREQ=WEEKLY;BYDAY=SU",
        starts_on=date(2026, 3, 29),
        ends_on=None,
        local_time=time(2, 30),
        tz=BERLIN,
        first_day=date(2026, 3, 29),
        last_day=date(2026, 3, 29),
    )
    assert got == [datetime(2026, 3, 29, 1, 30, tzinfo=UTC)]


def test_ambiguous_local_time_takes_first_occurrence() -> None:
    # 2026-10-25 02:30 в Берлине бывает дважды; берём первое (CEST, UTC+2) = 00:30 UTC.
    got = occurrences(
        "FREQ=WEEKLY;BYDAY=SU",
        starts_on=date(2026, 10, 25),
        ends_on=None,
        local_time=time(2, 30),
        tz=BERLIN,
        first_day=date(2026, 10, 25),
        last_day=date(2026, 10, 25),
    )
    assert got == [datetime(2026, 10, 25, 0, 30, tzinfo=UTC)]


def test_biweekly_parity_is_anchored_to_starts_on() -> None:
    # starts_on — понедельник 05.10; окно с 12.10: неделя 12.10 «нечётная», первая дата — 19.10.
    got = occurrences(
        "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO",
        starts_on=date(2026, 10, 5),
        ends_on=None,
        local_time=time(10, 0),
        tz=MSK,
        first_day=date(2026, 10, 12),
        last_day=date(2026, 11, 2),
    )
    assert [d.date() for d in got] == [date(2026, 10, 19), date(2026, 11, 2)]


def test_biweekly_with_two_days_per_week() -> None:
    got = occurrences(
        "FREQ=WEEKLY;INTERVAL=2;BYDAY=TU,TH",
        starts_on=date(2026, 10, 6),
        ends_on=None,
        local_time=time(10, 0),
        tz=MSK,
        first_day=date(2026, 10, 6),
        last_day=date(2026, 10, 25),
    )
    assert [d.date() for d in got] == [
        date(2026, 10, 6),
        date(2026, 10, 8),
        date(2026, 10, 20),
        date(2026, 10, 22),
    ]


def test_window_respects_starts_on_and_ends_on() -> None:
    got = occurrences(
        "FREQ=WEEKLY;BYDAY=MO,WE",
        starts_on=date(2026, 10, 14),  # среда: понедельник 12.10 раньше начала серии
        ends_on=date(2026, 10, 21),
        local_time=time(10, 0),
        tz=MSK,
        first_day=date(2026, 10, 1),
        last_day=date(2026, 12, 31),
    )
    assert [d.date() for d in got] == [date(2026, 10, 14), date(2026, 10, 19), date(2026, 10, 21)]


def test_window_boundaries_are_inclusive_and_empty_window_is_empty() -> None:
    got = occurrences(
        "FREQ=WEEKLY;BYDAY=MO",
        starts_on=date(2026, 10, 5),
        ends_on=None,
        local_time=time(10, 0),
        tz=MSK,
        first_day=date(2026, 10, 12),
        last_day=date(2026, 10, 19),
    )
    assert [d.date() for d in got] == [date(2026, 10, 12), date(2026, 10, 19)]
    empty = occurrences(
        "FREQ=WEEKLY;BYDAY=MO",
        starts_on=date(2026, 10, 5),
        ends_on=None,
        local_time=time(10, 0),
        tz=MSK,
        first_day=date(2026, 10, 20),
        last_day=date(2026, 10, 19),
    )
    assert empty == []
