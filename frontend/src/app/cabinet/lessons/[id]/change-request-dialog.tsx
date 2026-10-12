"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import {
  useCreateChangeRequest,
  useGetScheduleSettings,
} from "@/api/generated/endpoints/cabinet/cabinet";
import type { ChangeRequestType, LessonForFamilyDetail } from "@/api/generated/model";
import {
  createChangeRequestBodyCommentOneMax,
  createChangeRequestBodyProposedTextOneMax,
} from "@/api/generated/zod/cabinet/cabinet";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api-fetch";
import { isLateNow } from "@/lib/change-request-format";
import { applyApiErrors } from "@/lib/form-errors";
import { useMinuteNow } from "@/lib/use-minute-now";

import { invalidateMyLessons } from "./invalidate-my-lessons";

const PROPOSED_REQUIRED = "Укажите удобное время";

const commentShape = z
  .string()
  .max(createChangeRequestBodyCommentOneMax, `Не длиннее ${createChangeRequestBodyCommentOneMax} символов`);

const cancelSchema = z.object({ proposed_text: z.string(), comment: commentShape });
const rescheduleSchema = z.object({
  proposed_text: z
    .string()
    .trim()
    .min(1, PROPOSED_REQUIRED)
    .max(
      createChangeRequestBodyProposedTextOneMax,
      `Не длиннее ${createChangeRequestBodyProposedTextOneMax} символов`,
    ),
  comment: commentShape,
});

type Values = z.infer<typeof cancelSchema>;

const FIELDS = ["proposed_text", "comment"] as const;

const TITLES: Record<ChangeRequestType, string> = {
  reschedule: "Запросить перенос",
  cancel: "Запросить отмену",
};

function lateWarning(type: ChangeRequestType, hours: number): string {
  return type === "cancel"
    ? `До занятия меньше ${hours} ч — отмена будет засчитана как проведённое занятие`
    : "Если перенос не согласуют, занятие может быть засчитано как проведённое";
}

function RequestForm({
  type,
  lesson,
  onSent,
  onCancel,
}: {
  type: ChangeRequestType;
  lesson: LessonForFamilyDetail;
  onSent: () => void;
  onCancel: () => void;
}) {
  const queryClient = useQueryClient();
  const create = useCreateChangeRequest();
  const settings = useGetScheduleSettings();
  const minuteNow = useMinuteNow();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<Values>({
    resolver: zodResolver(type === "reschedule" ? rescheduleSchema : cancelSchema),
    defaultValues: { proposed_text: "", comment: "" },
  });

  const policyHours = settings.data?.cancel_policy_hours;
  const late =
    policyHours !== undefined && isLateNow(lesson.starts_at, policyHours, new Date(minuteNow));

  function onSubmit(values: Values) {
    setFormError(null);
    const proposed = values.proposed_text.trim();
    const comment = values.comment.trim();
    create.mutate(
      {
        lessonId: lesson.id,
        data: {
          type,
          ...(type === "reschedule" && proposed ? { proposed_text: proposed } : {}),
          ...(comment ? { comment } : {}),
        },
      },
      {
        onSuccess: () => {
          toast.success("Запрос отправлен репетитору");
          invalidateMyLessons(queryClient);
          onSent();
        },
        onError: (error) => {
          setFormError(applyApiErrors(error, setError, FIELDS));
          // Запрос уже есть или занятие изменилось: показываем актуальное состояние.
          if (error instanceof ApiError && error.status === 409) invalidateMyLessons(queryClient);
        },
      },
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
      {late && policyHours !== undefined && (
        <Alert>
          <AlertDescription>{lateWarning(type, policyHours)}</AlertDescription>
        </Alert>
      )}
      {settings.isError && (
        <Alert variant="destructive">
          <AlertDescription>Не удалось загрузить настройки. Обновите страницу.</AlertDescription>
        </Alert>
      )}
      {formError && (
        <Alert variant="destructive">
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      )}
      {type === "reschedule" && (
        <div className="flex flex-col gap-2">
          <Label htmlFor="cr-proposed">Когда удобно?</Label>
          <Textarea
            id="cr-proposed"
            maxLength={createChangeRequestBodyProposedTextOneMax}
            aria-invalid={errors.proposed_text ? true : undefined}
            {...register("proposed_text")}
          />
          {errors.proposed_text && (
            <p className="text-sm text-destructive">{errors.proposed_text.message}</p>
          )}
        </div>
      )}
      <div className="flex flex-col gap-2">
        <Label htmlFor="cr-comment">Комментарий</Label>
        <Textarea
          id="cr-comment"
          maxLength={createChangeRequestBodyCommentOneMax}
          aria-invalid={errors.comment ? true : undefined}
          {...register("comment")}
        />
        {errors.comment && <p className="text-sm text-destructive">{errors.comment.message}</p>}
      </div>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          Закрыть
        </Button>
        <Button type="submit" disabled={create.isPending || policyHours === undefined}>
          {create.isPending ? "Отправляем…" : "Отправить"}
        </Button>
      </div>
    </form>
  );
}

/** Запрос семьи на перенос или отмену занятия (`POST /me/lessons/{id}/change-requests`). */
export function ChangeRequestDialog({
  type,
  lesson,
  open,
  onOpenChange,
}: {
  type: ChangeRequestType;
  lesson: LessonForFamilyDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{TITLES[type]}</DialogTitle>
          <DialogDescription>Репетитор получит запрос и ответит на него.</DialogDescription>
        </DialogHeader>
        <RequestForm
          type={type}
          lesson={lesson}
          onSent={() => onOpenChange(false)}
          onCancel={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}
