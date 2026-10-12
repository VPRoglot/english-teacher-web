"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { useRejectChangeRequest } from "@/api/generated/endpoints/admin/admin";
import type { ChangeRequestAdminItem } from "@/api/generated/model";
import { rejectChangeRequestBodyTutorResponseMax } from "@/api/generated/zod/admin/admin";
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
import { applyApiErrors } from "@/lib/form-errors";
import { invalidateSchedule } from "@/lib/lesson-mutations";

const schema = z.object({
  tutor_response: z
    .string()
    .trim()
    .min(1, "Напишите ответ родителю")
    .max(
      rejectChangeRequestBodyTutorResponseMax,
      `Не длиннее ${rejectChangeRequestBodyTutorResponseMax} символов`,
    ),
});

type Values = z.infer<typeof schema>;

function RejectForm({
  request,
  onDone,
}: {
  request: ChangeRequestAdminItem;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const reject = useRejectChangeRequest();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { tutor_response: "" } });

  function onSubmit(values: Values) {
    setFormError(null);
    reject.mutate(
      { requestId: request.id, data: { tutor_response: values.tutor_response.trim() } },
      {
        onSuccess: () => {
          toast.success("Запрос отклонён");
          invalidateSchedule(queryClient);
          onDone();
        },
        onError: (error) => {
          setFormError(applyApiErrors(error, setError, ["tutor_response"]));
          // Запрос уже решён: показываем актуальную очередь.
          if (error instanceof ApiError && error.status === 409) invalidateSchedule(queryClient);
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
      <div className="flex flex-col gap-2">
        <Label htmlFor="reject-response">Ответ родителю</Label>
        <Textarea
          id="reject-response"
          maxLength={rejectChangeRequestBodyTutorResponseMax}
          aria-invalid={errors.tutor_response ? true : undefined}
          {...register("tutor_response")}
        />
        {errors.tutor_response && (
          <p className="text-sm text-destructive">{errors.tutor_response.message}</p>
        )}
      </div>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onDone}>
          Закрыть
        </Button>
        <Button type="submit" disabled={reject.isPending}>
          {reject.isPending ? "Отправляем…" : "Отклонить"}
        </Button>
      </div>
    </form>
  );
}

/** Отклонение запроса: обязательный ответ, который увидит родитель. */
export function RejectDialog({
  request,
  open,
  onOpenChange,
}: {
  request: ChangeRequestAdminItem;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Отклонить запрос</DialogTitle>
          <DialogDescription>Родитель увидит ваш ответ в кабинете.</DialogDescription>
        </DialogHeader>
        <RejectForm request={request} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}
