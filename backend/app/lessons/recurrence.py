"""Правила повторения занятий: разбор подмножества RRULE и развёртка в моменты UTC.

Чистые функции без БД. Поддерживается только `FREQ=WEEKLY` с обязательным `BYDAY` и
необязательным `INTERVAL` 1–4; границы серии задают `starts_on` и `ends_on`, а не правило.
"""

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr

MAX_INTERVAL = 4
_DAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
_ALLOWED_KEYS = ("FREQ", "INTERVAL", "BYDAY")


class InvalidRule(ValueError):  # noqa: N818 (имя из спеки плана)
    """Правило повторения не входит в поддерживаемое подмножество."""


def _parse_parts(rule: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for chunk in rule.split(";"):
        key, separator, value = chunk.partition("=")
        key, value = key.strip().upper(), value.strip().upper()
        if not separator or not key or not value:
            raise InvalidRule("Правило повторения записано неверно")
        if key not in _ALLOWED_KEYS:
            raise InvalidRule(f"Параметр {key} не поддерживается: допустимы FREQ, INTERVAL, BYDAY")
        if key in parts:
            raise InvalidRule(f"Параметр {key} указан дважды")
        parts[key] = value
    return parts


def normalize_rule(rule: str) -> str:
    """Каноническая запись правила: `FREQ=WEEKLY[;INTERVAL=n];BYDAY=…`, дни от MO к SU."""
    parts = _parse_parts(rule)
    if parts.get("FREQ") != "WEEKLY":
        raise InvalidRule("Поддерживается только еженедельное повторение (FREQ=WEEKLY)")
    interval = 1
    if "INTERVAL" in parts:
        raw_interval = parts["INTERVAL"]
        if not (raw_interval.isascii() and raw_interval.isdigit()):
            raise InvalidRule(f"Интервал должен быть числом от 1 до {MAX_INTERVAL}")
        interval = int(raw_interval)
        if not 1 <= interval <= MAX_INTERVAL:
            raise InvalidRule(f"Интервал должен быть от 1 до {MAX_INTERVAL}")
    if "BYDAY" not in parts:
        raise InvalidRule("Укажите дни недели (BYDAY)")
    days = [day.strip() for day in parts["BYDAY"].split(",")]
    if any(day not in _DAYS for day in days):
        raise InvalidRule("Дни недели задаются кодами MO, TU, WE, TH, FR, SA, SU")
    if len(set(days)) != len(days):
        raise InvalidRule("Дни недели не должны повторяться")
    ordered = sorted(days, key=_DAYS.index)
    interval_part = f";INTERVAL={interval}" if interval > 1 else ""
    return f"FREQ=WEEKLY{interval_part};BYDAY={','.join(ordered)}"


def occurrences(
    rule: str,
    *,
    starts_on: date,
    ends_on: date | None,
    local_time: time,
    tz: ZoneInfo,
    first_day: date,
    last_day: date,
) -> list[datetime]:
    """Моменты занятий (UTC) для местных дат окна `[first_day, last_day]` в пределах серии.

    Чётность недель при `INTERVAL > 1` отсчитывается от `starts_on`. Местное время
    переводится в UTC отдельно для каждой даты (`fold=0`): несуществующее время при
    переходе на летнее сдвигается вперёд, неоднозначное берёт первое вхождение.
    """
    first = max(starts_on, first_day)
    last = last_day if ends_on is None else min(ends_on, last_day)
    if first > last:
        return []
    series = rrulestr(normalize_rule(rule), dtstart=datetime.combine(starts_on, local_time))
    days = series.between(
        datetime.combine(first, time.min), datetime.combine(last, time.max), inc=True
    )
    return [datetime.combine(day.date(), local_time, tzinfo=tz).astimezone(UTC) for day in days]
