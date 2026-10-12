"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import {
  getGetLessonQueryKey,
  useUpdateLesson,
} from "@/api/generated/endpoints/admin/admin";
import type { AdminLessonDetail, LessonStatus } from "@/api/generated/model";
import { NATIVE_SELECT_CLASS } from "@/components/native-select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/form-errors";
import { LESSON_STATUS_LABELS } from "@/lib/lesson-format";
import { invalidateSchedule } from "@/lib/lesson-mutations";

const STATUSES = Object.keys(LESSON_STATUS_LABELS) as LessonStatus[];

/** Итоги «проведено» и «пропуск» ставятся только начавшемуся занятию (backend: 409 `lesson_not_started`). */
const NEEDS_STARTED: readonly LessonStatus[] = ["completed", "no_show"];

const LATE_CANCEL_HINT = "Засчитывается как проведённое";

/** Смена статуса занятия: `PATCH {status}`. */
export function LessonStatusSelect({ lesson, now }: { lesson: AdminLessonDetail; now: Date }) {
  const queryClient = useQueryClient();
  const update = useUpdateLesson();
  const [error, setError] = useState<string | null>(null);
  const future = new Date(lesson.starts_at).getTime() > now.getTime();

  function change(status: LessonStatus) {
    if (status === lesson.status) return;
    setError(null);
    update.mutate(
      { lessonId: lesson.id, data: { status } },
      {
        onSuccess: () => {
          toast.success("Статус обновлён");
          invalidateSchedule(queryClient); // и карточка занятия, и списки
        },
        onError: (e) => {
          setError(errorMessage(e));
          // Конфликт значит, что на сервере занятие уже другое: показываем актуальное.
          void queryClient.invalidateQueries({ queryKey: getGetLessonQueryKey(lesson.id) });
        },
      },
    );
  }

  return (
    <div className="flex max-w-xs flex-col gap-2">
      <Label htmlFor="lesson-status">Статус</Label>
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <select
        id="lesson-status"
        className={NATIVE_SELECT_CLASS}
        value={lesson.status}
        disabled={update.isPending}
        aria-describedby={lesson.status === "cancelled_late" ? "lesson-status-hint" : undefined}
        onChange={(event) => change(event.target.value as LessonStatus)}
      >
        {STATUSES.map((status) => (
          <option
            key={status}
            value={status}
            disabled={future && NEEDS_STARTED.includes(status) && status !== lesson.status}
            title={status === "cancelled_late" ? LATE_CANCEL_HINT : undefined}
          >
            {LESSON_STATUS_LABELS[status]}
          </option>
        ))}
      </select>
      {lesson.status === "cancelled_late" && (
        <p id="lesson-status-hint" className="text-sm text-muted-foreground">
          {LATE_CANCEL_HINT}
        </p>
      )}
    </div>
  );
}
