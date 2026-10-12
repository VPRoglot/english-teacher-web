# Ruling R4 — regeneration without resurrection, twins or note loss

Replaces the brief's delete-and-recreate `regenerate_series_from`. Binding for Task 2 (fix round 1) and Task 4.

## Problem
Delete-and-recreate with the frontier reset to `from_day − 1` brings back deleted lessons, creates scheduled twins next to moved (`is_detached`) and cancelled lessons, changes lesson ids and cascade-deletes notes written in advance. That violates spec 3.3 («Прошедшие, отмеченные и отсоединённые занятия не трогаются»), clarifications 1 and 3, and Review Focus 2.

## Data model change (edit migration 0005 in place — it is not merged yet)
- `lessons.occurrence_date date NULL` — the local date (tutor timezone at generation time) of the rule occurrence this lesson came from. Set by generation for every series lesson; NULL for one-off and trial lessons. It never changes when a lesson is moved (detached), so it identifies the occurrence.
- CHECK `series_occurrence`: `(series_id IS NULL) = (occurrence_date IS NULL)`.
- `UniqueConstraint("series_id", "occurrence_date", name="uq_lessons_series_id_occurrence_date")` in addition to the existing `uq_lessons_series_id_starts_at` (spec). Generation inserts with plain `ON CONFLICT DO NOTHING` (no target) so either constraint makes a retry idempotent.
- Test factory `make_lesson` / any helper that creates series lessons must set `occurrence_date`.

## Timezone change — shift in place, never regenerate
`async def shift_series_timezone(session, series: LessonSeries, *, old_tz: ZoneInfo, new_tz: ZoneInfo, now: datetime) -> list[Lesson]` in generation.py:
- For lessons of the series with `status = scheduled`, `is_detached = false`, `starts_at > now`: `starts_at = combine(lesson.occurrence_date, series.local_start_time, tzinfo=new_tz)` (fold=0) → UTC. Same row, same id, note kept.
- A lesson whose new instant is already in the past is still shifted (it becomes "нужно отметить"); it is not deleted.
- If the new instant collides with another lesson of the same series (`uq_lessons_series_id_starts_at`), leave that lesson unchanged and log warning `series_shift_conflict` (use a savepoint per lesson or pre-check).
- Frontier unchanged (it is a local date). Cancelled/completed/no_show/detached lessons, one-off and trial lessons keep their instant.
- `update_tutor_settings` calls it for each active series (locked in id order) when the timezone actually changes.

## Series edit — reconcile by occurrence date
Replace `regenerate_series_from` with:

```python
@dataclass(frozen=True)
class SeriesShape:  # the rule as it was before the edit
    rrule: str
    starts_on: date
    ends_on: date | None
    local_start_time: time
    generated_through: date | None

def series_shape(series: LessonSeries) -> SeriesShape: ...

@dataclass
class Reconciled:
    created: list[Lesson]
    updated: list[Lesson]   # existing rows changed in place (time/duration/url/series_id)

async def reconcile_series(session, series: LessonSeries, *, previous: SeriesShape,
                           lessons_from: LessonSeries | None = None,
                           from_day: date, tz: ZoneInfo, now: datetime) -> Reconciled
```
- `series` — the series AFTER the edit (in-place edit: the same row already mutated; split: the new series). `lessons_from` — whose existing lessons are reconciled (split: the old series; default: `series`). `previous` — snapshot of the old rule taken before mutation.
- `start = max(from_day, series.starts_on, today)`, `horizon = today + HORIZON_DAYS`. `new_dates` = local dates of `occurrences(series rule…)` in `[start, horizon]` whose instant ≥ now.
- `existing` = lessons of `lessons_from` with `occurrence_date >= start` (any status), keyed by `occurrence_date`.
- For each `d` in `new_dates`:
  - existing lesson for `d` that is `scheduled`, not detached, `starts_at > now` → UPDATE in place: `starts_at` (new local time on `d`), `duration_min`, `meeting_url`, `series_id = series.id` (moves it to the new series on split). Id and note kept.
  - existing lesson for `d` that is kept (detached, or any non-scheduled status, or already started) → leave it; create nothing for `d`.
  - no existing lesson, and `d` was an occurrence of `previous` with `d <= previous.generated_through` → the tutor deleted it → create nothing.
  - otherwise → INSERT (`occurrence_date = d`).
- Existing `scheduled`, non-detached, future lessons of `lessons_from` with `occurrence_date >= start` whose date is NOT in `new_dates` → DELETE (the date left the schedule).
- `series.generated_through = max(series.generated_through or start − 1 day, horizon)`.
- Returns created + updated (Task 4 computes overlap warnings for both).

## Daily materialization
`materialize_series` sets `occurrence_date` on inserts; otherwise unchanged (forward-only from the frontier).

## Tests that must exist (Task 2 fix round)
- timezone change: ids and notes of shifted lessons preserved; deleted lesson does not come back; detached and cancelled lessons keep their instant and get no twin; lesson later today whose new instant is past is shifted, not deleted.
- reconcile, in place (same rule, new time): ids and notes kept, times updated; deleted occurrence not recreated; detached/cancelled kept, no twin on their date.
- reconcile with a day change (TU → WE): TU scheduled future lessons deleted, WE created; a deleted TU occurrence does not block WE.
- reconcile as split (lessons_from = old series): updated lessons now belong to the new series; kept lessons stay with the old series.
- the old tests that asserted twins (17 new lessons; 05:00 UTC lesson next to the detached one) are rewritten to the new behaviour.
