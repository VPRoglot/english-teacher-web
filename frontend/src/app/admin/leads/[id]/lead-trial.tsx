"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import {
  useListTrialLessons,
  useScheduleTrial,
} from "@/api/generated/endpoints/admin/admin";
import type { LeadDetail, LeadStatus } from "@/api/generated/model";
import { scheduleTrialBodyDurationMinDefault } from "@/api/generated/zod/admin/admin";
import {
  LessonTimeFields,
  lessonTimeShape,
  meetingUrlShape,
} from "@/components/lesson-time-fields";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatLessonWhen, nextHourParts, zonedToUtcIso } from "@/lib/datetime";
import { ApiError } from "@/lib/api-fetch";
import { applyApiErrors, errorMessage } from "@/lib/form-errors";
import { LESSON_STATUS_LABELS } from "@/lib/lesson-format";
import { invalidateSchedule, toastWarnings } from "@/lib/lesson-mutations";
import { useTutorTimeZone, useTutorTimeZoneReady } from "@/lib/use-tutor-time-zone";

import { useRefreshLead } from "./use-refresh-lead";

/**
 * Статусы заявки, из которых можно назначить пробное: переходы в `trial_scheduled`
 * из таблицы спеки 3.2 (backend отвечает 409 из остальных).
 */
const SCHEDULABLE_STATUSES: readonly LeadStatus[] = ["new", "contacted"];

const schema = z.object({
  date: lessonTimeShape.date,
  time: lessonTimeShape.time,
  duration_min: lessonTimeShape.duration_min,
  meeting_url: meetingUrlShape,
});

type Values = z.infer<typeof schema>;

const FIELDS = ["duration_min", "meeting_url"] as const;

function TrialForm({
  lead,
  timeZone,
  ready,
  onSaved,
  onCancel,
}: {
  lead: LeadDetail;
  timeZone: string;
  ready: boolean;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const queryClient = useQueryClient();
  const refresh = useRefreshLead(lead.id);
  const schedule = useScheduleTrial();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      ...nextHourParts(timeZone),
      duration_min: scheduleTrialBodyDurationMinDefault,
      meeting_url: "",
    },
  });

  function onSubmit(values: Values) {
    setFormError(null);
    let startsAt: string;
    try {
      startsAt = zonedToUtcIso(values.date, values.time, timeZone);
    } catch (error) {
      setFormError(errorMessage(error));
      return;
    }
    schedule.mutate(
      {
        leadId: lead.id,
        data: {
          starts_at: startsAt,
          duration_min: values.duration_min,
          ...(values.meeting_url ? { meeting_url: values.meeting_url } : {}),
        },
      },
      {
        onSuccess: (saved) => {
          toast.success("Пробное занятие назначено");
          toastWarnings(saved.warnings);
          void refresh();
          invalidateSchedule(queryClient); // в том числе список пробных занятий заявки
          onSaved();
        },
        onError: (error) => {
          setFormError(applyApiErrors(error, setError, FIELDS));
          // Статус мог измениться в другой вкладке: показываем актуальное состояние.
          if (error instanceof ApiError && error.status === 409) void refresh();
        },
      },
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
      {formError && (
        <Alert variant="destructive">
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      )}
      <LessonTimeFields register={register} errors={errors} idPrefix="trial" />
      <div className="flex flex-col gap-2">
        <Label htmlFor="trial-url">Ссылка на занятие</Label>
        <Input
          id="trial-url"
          type="url"
          placeholder="Необязательно: https://…"
          aria-invalid={errors.meeting_url ? true : undefined}
          {...register("meeting_url")}
        />
        {errors.meeting_url && (
          <p className="text-sm text-destructive">{errors.meeting_url.message}</p>
        )}
      </div>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          Отмена
        </Button>
        <Button type="submit" disabled={!ready || schedule.isPending}>
          {schedule.isPending ? "Назначаем…" : "Назначить"}
        </Button>
      </div>
    </form>
  );
}

/**
 * Пробное занятие заявки: список пробных и назначение нового (`POST /admin/leads/{id}/trial`).
 * Время вводится в поясе репетитора. Пока пояс не загружен, отправка заблокирована,
 * а форма пересоздаётся при его загрузке, чтобы поля показывали время в настоящем поясе.
 */
export function LeadTrial({ lead }: { lead: LeadDetail }) {
  const [open, setOpen] = useState(false);
  const timeZone = useTutorTimeZone("admin");
  const ready = useTutorTimeZoneReady("admin");
  const trials = useListTrialLessons(lead.id);
  const canSchedule = SCHEDULABLE_STATUSES.includes(lead.status);

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold">Пробное занятие</h2>
      {trials.error && !trials.data && (
        <p className="text-sm text-muted-foreground">{errorMessage(trials.error)}</p>
      )}
      {trials.data &&
        (trials.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">Пробных занятий пока нет</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {trials.data.map((lesson) => (
              <li
                key={lesson.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2"
              >
                <span className="flex flex-wrap items-center gap-2 text-sm">
                  {formatLessonWhen(lesson.starts_at, lesson.duration_min, timeZone)}
                  <Badge variant="outline">{LESSON_STATUS_LABELS[lesson.status]}</Badge>
                </span>
                <Link
                  href={`/admin/lessons/${lesson.id}`}
                  className={buttonVariants({ variant: "outline", size: "sm" })}
                >
                  Открыть
                </Link>
              </li>
            ))}
          </ul>
        ))}
      {canSchedule && (
        <Button type="button" className="self-start" onClick={() => setOpen(true)}>
          Назначить пробное
        </Button>
      )}
      {/* Диалог не зависит от статуса: после 409 заявка обновляется, а ошибка остаётся на экране. */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Назначить пробное</DialogTitle>
            <DialogDescription>Время указывается в поясе репетитора.</DialogDescription>
          </DialogHeader>
          <TrialForm
            key={`${ready}:${timeZone}`}
            lead={lead}
            timeZone={timeZone}
            ready={ready}
            onSaved={() => setOpen(false)}
            onCancel={() => setOpen(false)}
          />
        </DialogContent>
      </Dialog>
    </section>
  );
}
