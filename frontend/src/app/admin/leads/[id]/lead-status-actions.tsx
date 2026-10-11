"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { UpdateLeadBody } from "@/api/generated/zod/admin/admin";
import { useUpdateLead } from "@/api/generated/endpoints/admin/admin";
import type { LeadDetail, LeadStatus, LeadUpdate } from "@/api/generated/model";
import { zodOptions } from "@/app/admin/site/site-form";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api-fetch";
import { applyApiErrors } from "@/lib/form-errors";

import { useRefreshLead } from "./use-refresh-lead";

type ManualStatus = "contacted" | "rejected";

/**
 * Статусы, в которые репетитор переводит заявку вручную, по текущему статусу.
 * Это таблица переходов из спеки 3.2 без `trial_scheduled` (его выставляет назначение пробного)
 * и `converted` (его выставляет конвертация); сверяется с таблицей спеки тестом.
 */
export const MANUAL_TRANSITIONS: Record<LeadStatus, ManualStatus[]> = {
  new: ["contacted", "rejected"],
  contacted: ["rejected"],
  trial_scheduled: ["contacted", "rejected"],
  rejected: ["contacted"],
  converted: [],
};

const ACTION_LABELS: Record<ManualStatus, string> = {
  contacted: "Связались",
  rejected: "Отказ",
};

/** Строковое правило поля из схемы API: там поле «строка или null, можно опустить». */
function stringRule(field: z.ZodOptional<z.ZodUnion<readonly [z.ZodString, z.ZodNull]>>) {
  return field.unwrap().options[0];
}

// Пробелы по краям отбрасываются до проверки, а правила длины берутся из схемы API.
const contactedSchema = z.object({
  comment: z.string().trim().pipe(stringRule(UpdateLeadBody.shape.comment)),
});
const rejectedSchema = z.object({
  reject_reason: z.string().trim().pipe(stringRule(UpdateLeadBody.shape.reject_reason)),
});

/** Отправка перехода статуса: тост, закрытие диалога, обновление карточки; 409 показывается в форме. */
function useStatusChange(leadId: string, onDone: () => void) {
  const refresh = useRefreshLead(leadId);
  const update = useUpdateLead();
  const [formError, setFormError] = useState<string | null>(null);

  function submit(data: LeadUpdate, describeError: (error: unknown) => string | null) {
    setFormError(null);
    update.mutate(
      { leadId, data },
      {
        onSuccess: () => {
          toast.success("Статус обновлён");
          // Прежний маршрут остаётся смонтированным (Activity): закрываем диалог до обновления данных.
          onDone();
          void refresh();
        },
        onError: (error) => {
          setFormError(describeError(error));
          // Конфликт значит, что статус на сервере уже другой: показываем актуальный.
          if (error instanceof ApiError && error.status === 409) void refresh();
        },
      },
    );
  }

  return { submit, formError, pending: update.isPending };
}

function DialogActions({ pending, onCancel }: { pending: boolean; onCancel: () => void }) {
  return (
    <DialogFooter>
      <Button type="button" variant="outline" onClick={onCancel}>
        Отмена
      </Button>
      <Button type="submit" disabled={pending}>
        Подтвердить
      </Button>
    </DialogFooter>
  );
}

function FormAlert({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <Alert variant="destructive">
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  );
}

function ContactedForm({ lead, onClose }: { lead: LeadDetail; onClose: () => void }) {
  const { submit, formError, pending } = useStatusChange(lead.id, onClose);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<z.input<typeof contactedSchema>, unknown, z.output<typeof contactedSchema>>({
    resolver: zodResolver(contactedSchema, zodOptions),
    defaultValues: { comment: "" },
  });

  return (
    <form
      noValidate
      className="flex flex-col gap-4"
      onSubmit={handleSubmit((values) =>
        submit({ status: "contacted", comment: values.comment || undefined }, (error) =>
          applyApiErrors(error, setError, ["comment"]),
        ),
      )}
    >
      <FormAlert message={formError} />
      <div className="flex flex-col gap-2">
        <Label htmlFor="contacted-comment">Комментарий</Label>
        <Textarea
          id="contacted-comment"
          placeholder="Необязательно: о чём договорились"
          aria-invalid={errors.comment ? true : undefined}
          {...register("comment")}
        />
        {errors.comment && <p className="text-sm text-destructive">{errors.comment.message}</p>}
      </div>
      <DialogActions pending={pending} onCancel={onClose} />
    </form>
  );
}

function RejectedForm({ lead, onClose }: { lead: LeadDetail; onClose: () => void }) {
  const { submit, formError, pending } = useStatusChange(lead.id, onClose);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<z.input<typeof rejectedSchema>, unknown, z.output<typeof rejectedSchema>>({
    resolver: zodResolver(rejectedSchema, zodOptions),
    defaultValues: { reject_reason: "" },
  });

  return (
    <form
      noValidate
      className="flex flex-col gap-4"
      onSubmit={handleSubmit((values) =>
        submit({ status: "rejected", reject_reason: values.reject_reason }, (error) =>
          applyApiErrors(error, setError, ["reject_reason"]),
        ),
      )}
    >
      <FormAlert message={formError} />
      <div className="flex flex-col gap-2">
        <Label htmlFor="reject-reason">Причина отказа</Label>
        <Textarea
          id="reject-reason"
          placeholder="Например: дорого, не подошло время"
          aria-invalid={errors.reject_reason ? true : undefined}
          {...register("reject_reason")}
        />
        {errors.reject_reason && (
          <p className="text-sm text-destructive">{errors.reject_reason.message}</p>
        )}
      </div>
      <DialogActions pending={pending} onCancel={onClose} />
    </form>
  );
}

export function LeadStatusActions({ lead }: { lead: LeadDetail }) {
  const [dialog, setDialog] = useState<ManualStatus | null>(null);
  const close = () => setDialog(null);

  return (
    <>
      <div className="flex flex-wrap gap-2">
        {MANUAL_TRANSITIONS[lead.status].map((status) => (
          <Button
            key={status}
            type="button"
            variant={status === "rejected" ? "outline" : "default"}
            onClick={() => setDialog(status)}
          >
            {ACTION_LABELS[status]}
          </Button>
        ))}
      </div>
      <Dialog open={dialog !== null} onOpenChange={(open) => !open && close()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{dialog === "rejected" ? "Отказ по заявке" : "Связались с семьёй"}</DialogTitle>
            <DialogDescription>
              {dialog === "rejected"
                ? "Причина сохранится в истории заявки. Позже заявку можно вернуть в работу."
                : "Комментарий сохранится в истории заявки."}
            </DialogDescription>
          </DialogHeader>
          {dialog === "contacted" && <ContactedForm lead={lead} onClose={close} />}
          {dialog === "rejected" && <RejectedForm lead={lead} onClose={close} />}
        </DialogContent>
      </Dialog>
    </>
  );
}
