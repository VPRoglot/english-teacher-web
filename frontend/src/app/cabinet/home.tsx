"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { useGetMe } from "@/api/generated/endpoints/auth/auth";
import { useListMyLessons } from "@/api/generated/endpoints/cabinet/cabinet";
import type { LessonForFamily } from "@/api/generated/model";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate, formatLessonWhen, timeZoneNote } from "@/lib/datetime";
import { errorMessage } from "@/lib/form-errors";
import { LESSON_STATUS_LABELS } from "@/lib/lesson-format";
import { useTutorTimeZone } from "@/lib/use-tutor-time-zone";

import { withChild } from "./child-link";
import { JoinButton } from "./join-button";
import { useSelectedChild } from "./use-selected-child";

const DAY_MS = 86_400_000;
const UPCOMING_DAYS = 28;
const NOTES_DAYS = 56;
const UPCOMING_LIMIT = 5;
const NOTES_LIMIT = 3;

const byStart = (a: LessonForFamily, b: LessonForFamily) =>
  new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime();

/** Границы запросов; «сейчас» фиксируется при открытии страницы, чтобы ключи запросов не менялись. */
function useWindows() {
  const [now] = useState(() => Date.now());
  return useMemo(
    () => ({
      upcoming: {
        from: new Date(now).toISOString(),
        to: new Date(now + UPCOMING_DAYS * DAY_MS).toISOString(),
      },
      notes: {
        from: new Date(now - NOTES_DAYS * DAY_MS).toISOString(),
        to: new Date(now).toISOString(),
      },
    }),
    [now],
  );
}

function When({ lesson, timeZone }: { lesson: LessonForFamily; timeZone: string }) {
  return <>{formatLessonWhen(lesson.starts_at, lesson.duration_min, timeZone)}</>;
}

function NearestLesson({
  lesson,
  timeZone,
  childId,
}: {
  lesson: LessonForFamily;
  timeZone: string;
  childId: string | null;
}) {
  const note = timeZoneNote(timeZone);
  return (
    <div className="flex flex-col items-start gap-3">
      <div className="flex flex-col gap-1">
        <Link
          href={withChild(`/cabinet/lessons/${lesson.id}`, childId)}
          className="text-base font-medium underline-offset-4 hover:underline"
        >
          <When lesson={lesson} timeZone={timeZone} />
        </Link>
        {note && <span className="text-xs text-muted-foreground">{note}</span>}
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span>{lesson.child_name}</span>
          <Badge variant="secondary">{LESSON_STATUS_LABELS[lesson.status]}</Badge>
        </div>
      </div>
      <JoinButton url={lesson.join_url} />
    </div>
  );
}

function ScheduleCards() {
  const me = useGetMe().data;
  const timeZone = useTutorTimeZone("cabinet");
  const { childId } = useSelectedChild();
  const windows = useWindows();
  const childParam = childId ? { child_id: childId } : {};

  const upcoming = useListMyLessons({ ...windows.upcoming, ...childParam });
  const past = useListMyLessons({ ...windows.notes, ...childParam });

  const scheduled = useMemo(
    () => (upcoming.data ?? []).filter((lesson) => lesson.status === "scheduled").sort(byStart),
    [upcoming.data],
  );
  const nearest = scheduled[0];
  const following = scheduled.slice(1, 1 + UPCOMING_LIMIT);
  const noted = useMemo(
    () =>
      (past.data ?? [])
        .filter((lesson) => lesson.has_shared_note)
        .sort(byStart)
        .reverse()
        .slice(0, NOTES_LIMIT),
    [past.data],
  );
  const showChild = (me?.children.length ?? 0) > 1;

  return (
    <>
      {(upcoming.error || past.error) && (
        <Alert variant="destructive">
          <AlertDescription>{errorMessage(upcoming.error ?? past.error)}</AlertDescription>
        </Alert>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Ближайшее занятие</CardTitle>
        </CardHeader>
        <CardContent>
          {nearest ? (
            <NearestLesson lesson={nearest} timeZone={timeZone} childId={childId} />
          ) : (
            upcoming.isSuccess && (
              <p className="text-sm text-muted-foreground">Ближайших занятий нет</p>
            )
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Предстоящие</CardTitle>
        </CardHeader>
        <CardContent>
          {following.length > 0 ? (
            <ul className="space-y-2 text-sm">
              {following.map((lesson) => (
                <li key={lesson.id}>
                  <Link
                    href={withChild(`/cabinet/lessons/${lesson.id}`, childId)}
                    className="underline-offset-4 hover:underline"
                  >
                    <When lesson={lesson} timeZone={timeZone} />
                    {showChild && ` · ${lesson.child_name}`}
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            upcoming.isSuccess && (
              <p className="text-sm text-muted-foreground">Других ближайших занятий нет</p>
            )
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Последние заметки</CardTitle>
        </CardHeader>
        <CardContent>
          {noted.length > 0 ? (
            <ul className="space-y-2 text-sm">
              {noted.map((lesson) => (
                <li key={lesson.id}>
                  <Link
                    href={withChild(`/cabinet/lessons/${lesson.id}`, childId)}
                    className="underline-offset-4 hover:underline"
                  >
                    {`${formatDate(lesson.starts_at, timeZone)} · ${lesson.child_name} — открыть заметку`}
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            past.isSuccess && <p className="text-sm text-muted-foreground">Заметок пока нет</p>
          )}
        </CardContent>
      </Card>
    </>
  );
}

/** Главная кабинета. Использует `useSearchParams` (выбранный ребёнок), поэтому рендерится под `Suspense`. */
export function Home() {
  const me = useGetMe().data;
  if (!me) return null;

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">Здравствуйте, {me.display_name}!</h1>
      <ScheduleCards />
      {me.role === "parent" && (
        <Card>
          <CardHeader>
            <CardTitle>Дети</CardTitle>
          </CardHeader>
          <CardContent>
            {me.children.length === 0 ? (
              <p className="text-sm text-muted-foreground">Детей пока нет.</p>
            ) : (
              <ul className="list-disc space-y-1 pl-5 text-sm">
                {me.children.map((child) => (
                  <li key={child.id}>{child.full_name}</li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      )}
    </>
  );
}
