"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { useGetMe } from "@/api/generated/endpoints/auth/auth";
import { useWithdrawChangeRequest } from "@/api/generated/endpoints/cabinet/cabinet";
import type {
  ChangeRequestForFamily,
  ChangeRequestType,
  LessonForFamilyDetail,
} from "@/api/generated/model";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  CHANGE_REQUEST_STATUS_LABELS,
  CHANGE_REQUEST_TYPE_LABELS,
} from "@/lib/change-request-format";
import { formatDateTime } from "@/lib/datetime";
import { useMinuteNow } from "@/lib/use-minute-now";
import { useTutorTimeZone } from "@/lib/use-tutor-time-zone";

import { ChangeRequestDialog } from "./change-request-dialog";
import { invalidateMyLessons } from "./invalidate-my-lessons";

function RequestSummary({ request, timeZone }: { request: ChangeRequestForFamily; timeZone: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border px-3 py-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{CHANGE_REQUEST_TYPE_LABELS[request.type]}</Badge>
        <span className="font-medium">{CHANGE_REQUEST_STATUS_LABELS[request.status]}</span>
        {request.type === "cancel" && request.is_late && (
          <Badge variant="secondary">Поздняя отмена</Badge>
        )}
      </div>
      <p className="text-muted-foreground">
        {`Отправлен ${formatDateTime(request.created_at, timeZone)}`}
      </p>
      {request.proposed_text && <p>{`Удобное время: ${request.proposed_text}`}</p>}
      {request.comment && <p>{`Комментарий: ${request.comment}`}</p>}
      {request.status === "rejected" && request.tutor_response && (
        <p>{`Ответ репетитора: ${request.tutor_response}`}</p>
      )}
      {request.status !== "rejected" && request.tutor_response && (
        <p>{`Комментарий репетитора: ${request.tutor_response}`}</p>
      )}
    </div>
  );
}

/**
 * Запрос на перенос или отмену занятия в кабинете: последний запрос со статусом и ответом
 * репетитора; родителю — кнопки подачи (нет ждущего запроса, занятие впереди) и отзыва.
 * Ребёнок запрос видит, но кнопок у него нет.
 */
export function ChangeRequestBlock({ lesson }: { lesson: LessonForFamilyDetail }) {
  const queryClient = useQueryClient();
  const me = useGetMe();
  const timeZone = useTutorTimeZone("cabinet");
  const now = useMinuteNow();
  const withdraw = useWithdrawChangeRequest();
  const [dialogType, setDialogType] = useState<ChangeRequestType | null>(null);
  const [lastType, setLastType] = useState<ChangeRequestType>("cancel");
  const [withdrawing, setWithdrawing] = useState(false);

  const request = lesson.change_request;
  const isParent = me.data?.role === "parent";
  const pending = request?.status === "pending";
  const canRequest =
    isParent &&
    !pending &&
    lesson.status === "scheduled" &&
    new Date(lesson.starts_at).getTime() > now;

  if (!request && !canRequest) return null;

  function open(type: ChangeRequestType) {
    setLastType(type);
    setDialogType(type);
  }

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold">Перенос и отмена</h2>
      {request && <RequestSummary request={request} timeZone={timeZone} />}
      {isParent && pending && request && (
        <>
          <Button
            type="button"
            variant="outline"
            className="self-start"
            onClick={() => setWithdrawing(true)}
          >
            Отозвать запрос
          </Button>
          <ConfirmDialog
            open={withdrawing}
            onOpenChange={setWithdrawing}
            title="Отозвать запрос?"
            description="Репетитор больше не увидит этот запрос как ждущий ответа."
            confirmLabel="Отозвать"
            onConfirm={async () => {
              try {
                await withdraw.mutateAsync({ requestId: request.id });
                toast.success("Запрос отозван");
              } finally {
                // И при 409 (запрос уже обработан) показываем актуальное состояние.
                invalidateMyLessons(queryClient);
              }
            }}
          />
        </>
      )}
      {canRequest && (
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" onClick={() => open("reschedule")}>
            Запросить перенос
          </Button>
          <Button type="button" variant="outline" onClick={() => open("cancel")}>
            Запросить отмену
          </Button>
        </div>
      )}
      <ChangeRequestDialog
        type={dialogType ?? lastType}
        lesson={lesson}
        open={dialogType !== null}
        onOpenChange={(next) => {
          if (!next) setDialogType(null);
        }}
      />
    </section>
  );
}
