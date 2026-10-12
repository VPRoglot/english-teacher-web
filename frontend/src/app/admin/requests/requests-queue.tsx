"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { useListChangeRequests } from "@/api/generated/endpoints/admin/admin";
import type { ChangeRequestAdminItem } from "@/api/generated/model";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  CHANGE_REQUEST_STATUS_LABELS,
  CHANGE_REQUEST_TYPE_LABELS,
} from "@/lib/change-request-format";
import { formatDateTime, formatLessonWhen } from "@/lib/datetime";
import { errorMessage } from "@/lib/form-errors";
import { useTutorTimeZone } from "@/lib/use-tutor-time-zone";

import { ApproveDialog } from "./approve-dialog";
import { RejectDialog } from "./reject-dialog";

type Tab = "pending" | "all";

const TABS: { value: Tab; label: string }[] = [
  { value: "pending", label: "Ждут ответа" },
  { value: "all", label: "Все" },
];

function RequestCard({
  request,
  timeZone,
  onApprove,
  onReject,
}: {
  request: ChangeRequestAdminItem;
  timeZone: string;
  onApprove: () => void;
  onReject: () => void;
}) {
  const { lesson } = request;
  return (
    <li className="flex flex-col gap-2 rounded-xl border p-4 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Link
          href={`/admin/families/${request.family.id}`}
          className="text-base font-medium hover:underline"
        >
          {request.child.full_name}
        </Link>
        <Badge variant="outline">{CHANGE_REQUEST_TYPE_LABELS[request.type]}</Badge>
        {request.type === "cancel" && request.is_late && (
          <Badge variant="secondary">Поздняя отмена</Badge>
        )}
      </div>
      <Link href={`/admin/lessons/${lesson.id}`} className="hover:underline">
        {`Занятие: ${formatLessonWhen(lesson.starts_at, lesson.duration_min, timeZone)}`}
      </Link>
      {request.proposed_text && <p>{`Удобное время: ${request.proposed_text}`}</p>}
      {request.comment && <p>{`Комментарий: ${request.comment}`}</p>}
      <p className="text-muted-foreground">
        {`${request.requested_by_name}, ${formatDateTime(request.created_at, timeZone)}`}
      </p>
      {request.status === "pending" ? (
        <div className="flex gap-2">
          <Button onClick={onApprove}>Одобрить</Button>
          <Button variant="outline" onClick={onReject}>
            Отклонить
          </Button>
        </div>
      ) : (
        <div className="flex flex-col gap-1">
          <span className="font-medium">{CHANGE_REQUEST_STATUS_LABELS[request.status]}</span>
          {request.tutor_response && <p>{`Ответ: ${request.tutor_response}`}</p>}
          {request.resolved_at && (
            <p className="text-muted-foreground">
              {`Решён ${formatDateTime(request.resolved_at, timeZone)}`}
            </p>
          )}
        </div>
      )}
    </li>
  );
}

export function RequestsQueue() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const timeZone = useTutorTimeZone("admin");
  const tab: Tab = params.get("tab") === "all" ? "all" : "pending";
  const [approving, setApproving] = useState<ChangeRequestAdminItem | null>(null);
  const [rejecting, setRejecting] = useState<ChangeRequestAdminItem | null>(null);

  const requests = useListChangeRequests(tab === "pending" ? { status: "pending" } : undefined);

  function selectTab(next: Tab) {
    router.replace(next === "pending" ? pathname : `${pathname}?tab=${next}`);
  }

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">Запросы</h1>
      <div role="tablist" aria-label="Запросы" className="flex gap-2">
        {TABS.map(({ value, label }) => (
          <Button
            key={value}
            role="tab"
            aria-selected={tab === value}
            variant={tab === value ? "default" : "outline"}
            onClick={() => selectTab(value)}
          >
            {label}
          </Button>
        ))}
      </div>
      {requests.error ? (
        <p className="text-sm text-muted-foreground">{errorMessage(requests.error)}</p>
      ) : !requests.data ? null : requests.data.length === 0 ? (
        <p className="text-sm text-muted-foreground">Запросов нет</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {requests.data.map((request) => (
            <RequestCard
              key={request.id}
              request={request}
              timeZone={timeZone}
              onApprove={() => setApproving(request)}
              onReject={() => setRejecting(request)}
            />
          ))}
        </ul>
      )}
      {approving && (
        <ApproveDialog
          request={approving}
          open
          onOpenChange={(open) => !open && setApproving(null)}
        />
      )}
      {rejecting && (
        <RejectDialog
          request={rejecting}
          open
          onOpenChange={(open) => !open && setRejecting(null)}
        />
      )}
    </>
  );
}
