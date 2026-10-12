"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { getGetLessonQueryKey, useUpdateLesson } from "@/api/generated/endpoints/admin/admin";
import type { AdminLessonDetail, LessonUpdate } from "@/api/generated/model";
import {
  LessonTimeFields,
  lessonTimeShape,
  meetingUrlShape,
} from "@/components/lesson-time-fields";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { utcToZonedParts, zonedToUtcIso } from "@/lib/datetime";
import { applyApiErrors, errorMessage } from "@/lib/form-errors";
import { invalidateSchedule, toastWarnings } from "@/lib/lesson-mutations";
import { useTutorTimeZone, useTutorTimeZoneReady } from "@/lib/use-tutor-time-zone";

const schema = z.object({
  date: lessonTimeShape.date,
  time: lessonTimeShape.time,
  duration_min: lessonTimeShape.duration_min,
  meeting_url: meetingUrlShape,
});

type Values = z.infer<typeof schema>;

const FIELDS = ["duration_min", "meeting_url"] as const;

function EditLessonForm({
  lesson,
  timeZone,
  ready,
  onSaved,
}: {
  lesson: AdminLessonDetail;
  timeZone: string;
  ready: boolean;
  onSaved: () => void;
}) {
  const queryClient = useQueryClient();
  const update = useUpdateLesson();
  const [formError, setFormError] = useState<string | null>(null);
  const initial = utcToZonedParts(lesson.starts_at, timeZone);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      date: initial.date,
      time: initial.time,
      duration_min: lesson.duration_min,
      meeting_url: lesson.meeting_url ?? "",
    },
  });
  // Занятие отделяется от серии, только если сдвигается время; о длительности и ссылке не предупреждаем.
  const willDetach = lesson.series_id !== null && !lesson.is_detached;

  function onSubmit(values: Values) {
    setFormError(null);
    const data: LessonUpdate = {};
    try {
      if (values.date !== initial.date || values.time !== initial.time) {
        data.starts_at = zonedToUtcIso(values.date, values.time, timeZone);
      }
    } catch (error) {
      setFormError(errorMessage(error));
      return;
    }
    if (values.duration_min !== lesson.duration_min) data.duration_min = values.duration_min;
    const meetingUrl = values.meeting_url === "" ? null : values.meeting_url;
    if (meetingUrl !== lesson.meeting_url) data.meeting_url = meetingUrl;
    if (Object.keys(data).length === 0) {
      onSaved();
      return;
    }

    update.mutate(
      { lessonId: lesson.id, data },
      {
        onSuccess: (saved) => {
          toast.success("Занятие обновлено");
          toastWarnings(saved.warnings);
          void queryClient.invalidateQueries({ queryKey: getGetLessonQueryKey(lesson.id) });
          invalidateSchedule(queryClient);
          onSaved();
        },
        onError: (error) => {
          setFormError(applyApiErrors(error, setError, FIELDS));
          // Конфликт значит, что занятие на сервере уже другое (статус, время): показываем актуальное.
          void queryClient.invalidateQueries({ queryKey: getGetLessonQueryKey(lesson.id) });
        },
      },
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
      {willDetach && (
        <Alert>
          <AlertDescription>Занятие отделится от расписания</AlertDescription>
        </Alert>
      )}
      {formError && (
        <Alert variant="destructive">
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      )}
      <LessonTimeFields register={register} errors={errors} idPrefix="lesson-edit" />
      <div className="flex flex-col gap-2">
        <Label htmlFor="lesson-edit-url">Ссылка на занятие</Label>
        <Input
          id="lesson-edit-url"
          type="url"
          placeholder="https://"
          aria-invalid={errors.meeting_url ? true : undefined}
          {...register("meeting_url")}
        />
        {errors.meeting_url && (
          <p className="text-sm text-destructive">{errors.meeting_url.message}</p>
        )}
      </div>
      <Button type="submit" disabled={!ready || update.isPending}>
        {update.isPending ? "Сохраняем…" : "Сохранить"}
      </Button>
    </form>
  );
}

/**
 * Перенос занятия, правка длительности и ссылки (`PATCH`; backend разрешает это только для `scheduled`).
 * Местные дата и время — в поясе репетитора. Пока пояс не загружен, отправка заблокирована,
 * а форма пересоздаётся при его загрузке, чтобы поля показывали время в настоящем поясе.
 */
export function EditLessonDialog({
  lesson,
  open,
  onOpenChange,
}: {
  lesson: AdminLessonDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const timeZone = useTutorTimeZone("admin");
  const ready = useTutorTimeZoneReady("admin");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Перенести занятие</DialogTitle>
          <DialogDescription>Время указывается в поясе репетитора.</DialogDescription>
        </DialogHeader>
        <EditLessonForm
          key={`${ready}:${timeZone}`}
          lesson={lesson}
          timeZone={timeZone}
          ready={ready}
          onSaved={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}
