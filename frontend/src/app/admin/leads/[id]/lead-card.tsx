"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";

import { useGetLead, useUpdateLead } from "@/api/generated/endpoints/admin/admin";
import type { LeadDetail } from "@/api/generated/model";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { formatDateTime } from "@/lib/datetime";
import { errorMessage } from "@/lib/form-errors";
import {
  CONTACT_METHOD_LABELS,
  LEAD_STATUS_BADGE_VARIANTS,
  LEAD_STATUS_LABELS,
  leadContactHref,
} from "@/lib/lead-format";
import { useTutorTimeZone } from "@/lib/use-tutor-time-zone";

import { LeadConvertDialog } from "./lead-convert-dialog";
import { LeadHistory } from "./lead-history";
import { LeadStatusActions } from "./lead-status-actions";
import { useRefreshLead } from "./use-refresh-lead";

const COMMENT_MAX_LENGTH = 2000;

function ageLabel(age: number): string {
  const lastTwo = age % 100;
  const last = age % 10;
  if (lastTwo >= 11 && lastTwo <= 14) return `${age} лет`;
  if (last === 1) return `${age} год`;
  if (last >= 2 && last <= 4) return `${age} года`;
  return `${age} лет`;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="text-sm whitespace-pre-line">{children}</dd>
    </div>
  );
}

function LeadFields({ lead }: { lead: LeadDetail }) {
  const timeZone = useTutorTimeZone("admin");
  const utm = [lead.utm_source, lead.utm_medium, lead.utm_campaign].filter(Boolean).join(" / ");
  return (
    <dl className="grid gap-4 sm:grid-cols-2">
      <Field label="Ребёнок">{`${lead.child_name}, ${ageLabel(lead.child_age)}`}</Field>
      <Field label="Контакт">
        <a href={leadContactHref(lead)} className="underline underline-offset-2">
          {`${CONTACT_METHOD_LABELS[lead.contact_method]} · ${lead.phone}`}
        </a>
      </Field>
      {lead.messenger_handle && <Field label="Ник в мессенджере">{lead.messenger_handle}</Field>}
      {lead.goal && <Field label="Цель">{lead.goal}</Field>}
      {lead.preferred_time && <Field label="Удобное время">{lead.preferred_time}</Field>}
      {lead.reject_reason && <Field label="Причина отказа">{lead.reject_reason}</Field>}
      {utm && <Field label="UTM">{utm}</Field>}
      <Field label="Получена">{formatDateTime(lead.created_at, timeZone)}</Field>
    </dl>
  );
}

function TutorComment({ lead }: { lead: LeadDetail }) {
  const [draft, setDraft] = useState(lead.tutor_comment ?? "");
  const [error, setError] = useState<string | null>(null);
  const refresh = useRefreshLead(lead.id);
  const update = useUpdateLead();
  const dirty = draft.trim() !== (lead.tutor_comment ?? "");

  function save() {
    setError(null);
    update.mutate(
      { leadId: lead.id, data: { tutor_comment: draft.trim() } },
      {
        onSuccess: () => {
          toast.success("Комментарий сохранён");
          void refresh();
        },
        onError: (e) => setError(errorMessage(e)),
      },
    );
  }

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold">Комментарий</h2>
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <div className="flex flex-col gap-2">
        <Label htmlFor="lead-comment">Комментарий репетитора</Label>
        <Textarea
          id="lead-comment"
          maxLength={COMMENT_MAX_LENGTH}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
      </div>
      <Button
        type="button"
        className="self-start"
        disabled={!dirty || update.isPending}
        onClick={save}
      >
        Сохранить комментарий
      </Button>
    </section>
  );
}

function Skeleton() {
  return (
    <div role="status" aria-label="Загрузка" className="animate-pulse space-y-4">
      <div className="h-8 w-64 rounded-lg bg-muted" />
      <div className="h-32 rounded-xl bg-muted" />
    </div>
  );
}

export function LeadCard() {
  const { id } = useParams<{ id: string }>();
  const lead = useGetLead(id);

  if (lead.error && !lead.data) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p className="text-sm text-muted-foreground">{errorMessage(lead.error)}</p>
        <Link href="/admin/leads" className="text-sm underline underline-offset-2">
          К списку заявок
        </Link>
      </div>
    );
  }
  if (!lead.data) return <Skeleton />;

  const data = lead.data;
  return (
    <>
      <div className="flex flex-col gap-3">
        <Link href="/admin/leads" className="text-sm text-muted-foreground hover:text-foreground">
          Все заявки
        </Link>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">{data.parent_name}</h1>
          <Badge variant={LEAD_STATUS_BADGE_VARIANTS[data.status]}>
            {LEAD_STATUS_LABELS[data.status]}
          </Badge>
        </div>
      </div>
      <LeadFields lead={data} />
      <section className="flex flex-wrap items-start gap-2">
        <LeadStatusActions lead={data} />
        <LeadConvertDialog lead={data} />
        {data.status === "converted" && data.family_id && (
          <Link href={`/admin/families/${data.family_id}`} className={buttonVariants()}>
            Открыть семью
          </Link>
        )}
      </section>
      <TutorComment lead={data} />
      <LeadHistory history={data.history} />
    </>
  );
}
