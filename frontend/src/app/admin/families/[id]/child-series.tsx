"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import {
  useArchiveSeries,
  useListSeries,
  useUpdateSeries,
} from "@/api/generated/endpoints/admin/admin";
import type { ChildDetail, SeriesDetail, SeriesUpdate } from "@/api/generated/model";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Button } from "@/components/ui/button";
import { formatDate, todayInZone } from "@/lib/datetime";
import { errorMessage } from "@/lib/form-errors";
import { buildRule, describeSeries, parseRule } from "@/lib/lesson-format";
import { invalidateSchedule, lessonsCount, toastWarnings } from "@/lib/lesson-mutations";
import { useTutorTimeZone, useTutorTimeZoneReady } from "@/lib/use-tutor-time-zone";

import { SeriesFormDialog, type SeriesEditValues } from "../../series-form-dialog";

const ARCHIVE_DESCRIPTION =
  "Будущие занятия этого расписания будут удалены. Прошедшие и отмеченные останутся.";

/** Каноническая запись правила серии: сравнивается с тем, что собрала форма. */
function canonicalRule(rrule: string): string {
  const { days, interval } = parseRule(rrule);
  return buildRule({ days, interval: Math.min(Math.max(interval, 1), 4) as 1 | 2 | 3 | 4 });
}

/** Только поля, которые отличаются от серии: остальные backend оставляет как есть. */
function changedFields(series: SeriesDetail, values: SeriesEditValues): SeriesUpdate {
  const changes: SeriesUpdate = {};
  if (values.rrule !== canonicalRule(series.rrule)) changes.rrule = values.rrule;
  if (values.local_start_time !== series.local_start_time.slice(0, 5)) {
    changes.local_start_time = values.local_start_time;
  }
  if (values.duration_min !== series.duration_min) changes.duration_min = values.duration_min;
  if (values.meeting_url !== (series.meeting_url ?? null)) changes.meeting_url = values.meeting_url;
  if (values.ends_on !== (series.ends_on ?? null)) changes.ends_on = values.ends_on;
  return changes;
}

function SeriesRow({
  series,
  timeZone,
  onEdit,
  onArchive,
}: {
  series: SeriesDetail;
  timeZone: string;
  onEdit: () => void;
  onArchive: () => void;
}) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3">
      <div className="flex flex-col gap-0.5 text-sm">
        <span className="font-medium">{describeSeries(series)}</span>
        <span className="text-muted-foreground">
          <span>{`с ${formatDate(series.starts_on, timeZone)}`}</span>
          {series.ends_on && <span>{` по ${formatDate(series.ends_on, timeZone)}`}</span>}
        </span>
      </div>
      <div className="flex gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-label="Изменить расписание"
          onClick={onEdit}
        >
          Изменить
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-label="Завершить расписание"
          onClick={onArchive}
        >
          Завершить
        </Button>
      </div>
    </li>
  );
}

/** Блок «Расписание» активного ребёнка: регулярные занятия, их правка «с даты» и завершение. */
export function ChildSeries({ child }: { child: ChildDetail }) {
  const queryClient = useQueryClient();
  const timeZone = useTutorTimeZone("admin");
  const list = useListSeries({ child_id: child.id });
  const updateSeries = useUpdateSeries();
  const archiveSeries = useArchiveSeries();
  const [editing, setEditing] = useState<SeriesDetail | null>(null);
  const [archiving, setArchiving] = useState<SeriesDetail | null>(null);

  const ready = useTutorTimeZoneReady("admin");

  // «Сегодня» зависит от пояса: пока он запасной, список не показываем и не фильтруем.
  const today = todayInZone(timeZone);
  // Серия, у которой окончание уже прошло, больше ничего не создаёт: в списке она не нужна.
  const active = (list.data ?? []).filter(
    (series) => series.archived_at === null && (series.ends_on === null || series.ends_on >= today),
  );

  async function submitEdit(series: SeriesDetail, values: SeriesEditValues) {
    const data = changedFields(series, values);
    if (Object.keys(data).length === 0) return;
    const saved = await updateSeries.mutateAsync({
      seriesId: series.id,
      data,
      params: { scope: "this_and_following", from: values.from },
    });
    toast.success(`Расписание изменено: ${lessonsCount(saved.lessons_created)}`);
    toastWarnings(saved.warnings);
    invalidateSchedule(queryClient);
  }

  async function archive(series: SeriesDetail) {
    await archiveSeries.mutateAsync({ seriesId: series.id });
    toast.success("Расписание завершено");
    invalidateSchedule(queryClient);
  }

  return (
    <section className="flex flex-col gap-2 border-t pt-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Расписание</h3>
        <SeriesFormDialog mode="create" childId={child.id} />
      </div>
      {list.error ? (
        <p className="text-sm text-destructive">{errorMessage(list.error)}</p>
      ) : list.isPending || !ready ? (
        <p className="text-sm text-muted-foreground">Загружаем расписание…</p>
      ) : active.length === 0 ? (
        <p className="text-sm text-muted-foreground">Регулярных занятий нет</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {active.map((series) => (
            <SeriesRow
              key={series.id}
              series={series}
              timeZone={timeZone}
              onEdit={() => setEditing(series)}
              onArchive={() => setArchiving(series)}
            />
          ))}
        </ul>
      )}
      {editing && (
        <SeriesFormDialog
          key={editing.id}
          mode="edit"
          series={editing}
          open
          onOpenChange={(open) => {
            if (!open) setEditing(null);
          }}
          onEditSubmit={(values) => submitEdit(editing, values)}
        />
      )}
      {archiving && (
        <ConfirmDialog
          key={archiving.id}
          open
          onOpenChange={(open) => {
            if (!open) setArchiving(null);
          }}
          title="Завершить расписание?"
          description={ARCHIVE_DESCRIPTION}
          confirmLabel="Завершить"
          onConfirm={() => archive(archiving)}
        />
      )}
    </section>
  );
}
