"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { useGetDashboard } from "@/api/generated/endpoints/admin/admin";
import type { AdminLessonItem } from "@/api/generated/model";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CHANGE_REQUEST_TYPE_LABELS } from "@/lib/change-request-format";
import { formatDateTime, formatLessonWhen } from "@/lib/datetime";
import { errorMessage } from "@/lib/form-errors";
import { NEEDS_MARKING_LABEL } from "@/lib/lesson-format";

/** «8 лет», «1 год», «3 года»: склонение по последним цифрам. */
function agePhrase(age: number): string {
  const lastTwo = age % 100;
  const last = age % 10;
  if (lastTwo >= 11 && lastTwo <= 14) return `${age} лет`;
  if (last === 1) return `${age} год`;
  if (last >= 2 && last <= 4) return `${age} года`;
  return `${age} лет`;
}

function DashboardCard({
  title,
  total,
  empty,
  isEmpty,
  action,
  children,
}: {
  title: string;
  total: number;
  empty: string;
  isEmpty: boolean;
  action?: { href: string; label: string };
  children: ReactNode;
}) {
  const headingId = `dashboard-${title.replace(/\s+/g, "-")}`;
  return (
    <Card role="region" aria-labelledby={headingId}>
      <CardHeader>
        <CardTitle>
          <h2 id={headingId}>{`${title} · ${total}`}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col items-start gap-3">
        {isEmpty ? <p className="text-sm text-muted-foreground">{empty}</p> : children}
        {action && (
          <Link href={action.href} className={buttonVariants({ variant: "outline" })}>
            {action.label}
          </Link>
        )}
      </CardContent>
    </Card>
  );
}

function LessonList({ lessons, timeZone }: { lessons: AdminLessonItem[]; timeZone: string }) {
  return (
    <ul className="flex flex-col gap-2 text-sm">
      {lessons.map((lesson) => (
        <li key={lesson.id} className="flex flex-col">
          <Link href={`/admin/lessons/${lesson.id}`} className="underline underline-offset-2">
            {lesson.student.name}
          </Link>
          <span className="text-muted-foreground">
            {formatLessonWhen(lesson.starts_at, lesson.duration_min, timeZone)}
          </span>
        </li>
      ))}
    </ul>
  );
}

function Skeleton() {
  return (
    <div role="status" aria-label="Загрузка" className="grid animate-pulse gap-4 md:grid-cols-2">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="h-40 rounded-xl bg-muted" />
      ))}
    </div>
  );
}

export function Dashboard() {
  const dashboard = useGetDashboard();

  if (dashboard.error && !dashboard.data) {
    return <p className="text-sm text-muted-foreground">{errorMessage(dashboard.error)}</p>;
  }
  if (!dashboard.data) return <Skeleton />;

  const { new_leads, pending_requests, needs_marking, today, timezone } = dashboard.data;

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <DashboardCard
        title="Новые заявки"
        total={new_leads.total}
        isEmpty={new_leads.items.length === 0}
        empty="Новых заявок нет"
        action={{ href: "/admin/leads?status=new", label: "Все заявки" }}
      >
        <ul className="flex flex-col gap-2 text-sm">
          {new_leads.items.map((lead) => (
            <li key={lead.id} className="flex flex-col">
              <Link href={`/admin/leads/${lead.id}`} className="underline underline-offset-2">
                {lead.parent_name}
              </Link>
              <span className="text-muted-foreground">
                {`${lead.child_name}, ${agePhrase(lead.child_age)} · ${formatDateTime(lead.created_at, timezone)}`}
              </span>
            </li>
          ))}
        </ul>
      </DashboardCard>
      <DashboardCard
        title="Ждут ответа"
        total={pending_requests.total}
        isEmpty={pending_requests.items.length === 0}
        empty="Запросов нет"
        action={{ href: "/admin/requests", label: "Открыть очередь" }}
      >
        <ul className="flex flex-col gap-2 text-sm">
          {pending_requests.items.map((request) => (
            <li key={request.id} className="flex flex-col">
              <span>
                <span className="font-medium">{CHANGE_REQUEST_TYPE_LABELS[request.type]}</span>
                {`: ${request.child.full_name}`}
              </span>
              <span className="text-muted-foreground">
                {formatLessonWhen(request.lesson.starts_at, request.lesson.duration_min, timezone)}
              </span>
            </li>
          ))}
        </ul>
      </DashboardCard>
      <DashboardCard
        title={NEEDS_MARKING_LABEL}
        total={needs_marking.total}
        isEmpty={needs_marking.items.length === 0}
        empty="Все занятия отмечены"
      >
        <LessonList lessons={needs_marking.items} timeZone={timezone} />
      </DashboardCard>
      <DashboardCard
        title="Сегодня"
        total={today.length}
        isEmpty={today.length === 0}
        empty="Сегодня занятий нет"
      >
        <LessonList lessons={today} timeZone={timezone} />
      </DashboardCard>
    </div>
  );
}
