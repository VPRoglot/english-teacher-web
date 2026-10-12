"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { useApproveChangeRequest } from "@/api/generated/endpoints/admin/admin";
import type { ChangeRequestAdminItem } from "@/api/generated/model";
import { LessonTimeFields, lessonTimeShape } from "@/components/lesson-time-fields";
import { TutorSettingsError } from "@/components/tutor-settings-error";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ApiError } from "@/lib/api-fetch";
import { utcToZonedParts, zonedToUtcIso } from "@/lib/datetime";
import { errorMessage } from "@/lib/form-errors";
import { invalidateSchedule, toastWarnings } from "@/lib/lesson-mutations";
import { useTutorTimeZoneStatus } from "@/lib/use-tutor-time-zone";

const schema = z.object({ date: lessonTimeShape.date, time: lessonTimeShape.time });
type Values = z.infer<typeof schema>;

/** Ошибка 422 на `new_starts_at` (например, «совпадает с текущим») — показываем у поля времени. */
function newStartsAtIssue(error: unknown): string | null {
  if (!(error instanceof ApiError) || !Array.isArray(error.details.fields)) return null;
  for (const issue of error.details.fields as { loc?: unknown; message?: unknown }[]) {
    const loc = issue.loc;
    if (
      Array.isArray(loc) &&
      loc[loc.length - 1] === "new_starts_at" &&
      typeof issue.message === "string"
    ) {
      return issue.message;
    }
  }
  return null;
}

function ApproveForm({
  request,
  timeZone,
  ready,
  onDone,
}: {
  request: ChangeRequestAdminItem;
  timeZone: string;
  ready: boolean;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const approve = useApproveChangeRequest();
  const [formError, setFormError] = useState<string | null>(null);
  const isReschedule = request.type === "reschedule";
  const initial = utcToZonedParts(request.lesson.starts_at, timeZone);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: initial });

  function send(newStartsAt: string | null) {
    setFormError(null);
    approve.mutate(
      { requestId: request.id, data: newStartsAt ? { new_starts_at: newStartsAt } : {} },
      {
        onSuccess: (resolved) => {
          toast.success("Запрос одобрен");
          toastWarnings(resolved.warnings);
          invalidateSchedule(queryClient); // расписание, очередь и дашборд
          onDone();
        },
        onError: (error) => {
          const fieldIssue = newStartsAtIssue(error);
          if (fieldIssue) setError("time", { message: fieldIssue });
          else setFormError(errorMessage(error));
          // Запрос уже решён или занятие изменилось: показываем актуальную очередь.
          if (error instanceof ApiError && error.status === 409) invalidateSchedule(queryClient);
        },
      },
    );
  }

  function onSubmit(values: Values) {
    let startsAt: string;
    try {
      startsAt = zonedToUtcIso(values.date, values.time, timeZone);
    } catch (error) {
      setFormError(errorMessage(error));
      return;
    }
    send(startsAt);
  }

  const submit = (
    <Button type="submit" disabled={!ready || approve.isPending}>
      {approve.isPending ? "Одобряем…" : "Одобрить"}
    </Button>
  );
  const alert = formError && (
    <Alert variant="destructive">
      <AlertDescription>{formError}</AlertDescription>
    </Alert>
  );

  if (!isReschedule) {
    return (
      <form
        onSubmit={(event) => {
          event.preventDefault();
          send(null);
        }}
        className="flex flex-col gap-4"
      >
        {alert}
        <Alert>
          <AlertDescription>
            {request.is_late
              ? "Отмена поздняя — занятие будет засчитано как проведённое"
              : "Занятие будет отменено"}
          </AlertDescription>
        </Alert>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onDone}>
            Закрыть
          </Button>
          <Button type="submit" disabled={approve.isPending}>
            {approve.isPending ? "Одобряем…" : "Одобрить"}
          </Button>
        </div>
      </form>
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
      {alert}
      <LessonTimeFields
        register={register}
        errors={errors}
        idPrefix="approve"
        withDuration={false}
      />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onDone}>
          Закрыть
        </Button>
        {submit}
      </div>
    </form>
  );
}

/**
 * Одобрение запроса. Отмена — подтверждение с предупреждением о поздней отмене; перенос —
 * новые дата и время в поясе репетитора (предзаполнены текущим временем занятия). Пока пояс не
 * загружен, отправка заблокирована, а форма пересоздаётся при его загрузке.
 */
export function ApproveDialog({
  request,
  open,
  onOpenChange,
}: {
  request: ChangeRequestAdminItem;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { timeZone, ready, error } = useTutorTimeZoneStatus("admin");
  const reschedule = request.type === "reschedule";
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{reschedule ? "Одобрить перенос" : "Одобрить отмену"}</DialogTitle>
          <DialogDescription>
            {reschedule ? "Время указывается в поясе репетитора." : "Родитель увидит решение в кабинете."}
          </DialogDescription>
        </DialogHeader>
        {reschedule && error ? (
          <TutorSettingsError />
        ) : (
          <ApproveForm
            key={`${ready}:${timeZone}`}
            request={request}
            timeZone={timeZone}
            ready={ready}
            onDone={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
