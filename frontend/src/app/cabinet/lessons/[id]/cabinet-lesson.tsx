"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { useGetMyLesson } from "@/api/generated/endpoints/cabinet/cabinet";
import { Markdown } from "@/components/site/markdown";
import { Badge } from "@/components/ui/badge";
import { formatLessonWhen, timeZoneNote } from "@/lib/datetime";
import { ApiError } from "@/lib/api-fetch";
import { errorMessage } from "@/lib/form-errors";
import { LESSON_STATUS_LABELS } from "@/lib/lesson-format";
import { useTutorTimeZone } from "@/lib/use-tutor-time-zone";

import { withChild } from "../../child-link";
import { JoinButton } from "../../join-button";
import { useSelectedChild } from "../../use-selected-child";

const NOT_FOUND_TEXT = "Занятие не найдено";

function Skeleton() {
  return (
    <div role="status" aria-label="Загрузка" className="animate-pulse space-y-4">
      <div className="h-8 w-64 rounded-lg bg-muted" />
      <div className="h-32 rounded-xl bg-muted" />
    </div>
  );
}

/** Страница занятия в кабинете семьи: детали и общая заметка репетитора. Под `Suspense` (`useSearchParams`). */
export function CabinetLesson() {
  const { id } = useParams<{ id: string }>();
  const lesson = useGetMyLesson(id);
  const timeZone = useTutorTimeZone("cabinet");
  const { childId } = useSelectedChild();
  const backLink = (
    <Link
      href={withChild("/cabinet/calendar", childId)}
      className="text-sm text-muted-foreground hover:text-foreground"
    >
      ← К календарю
    </Link>
  );

  if (lesson.error && !lesson.data) {
    const text =
      lesson.error instanceof ApiError && lesson.error.status === 404
        ? NOT_FOUND_TEXT
        : errorMessage(lesson.error);
    return (
      <div className="flex flex-col items-start gap-3">
        {backLink}
        <p className="text-sm text-muted-foreground">{text}</p>
      </div>
    );
  }
  if (!lesson.data) return <Skeleton />;

  const data = lesson.data;
  const note = timeZoneNote(timeZone);

  return (
    <>
      <div className="flex flex-col gap-3">
        {backLink}
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">{data.child_name}</h1>
          <Badge variant="secondary">{LESSON_STATUS_LABELS[data.status]}</Badge>
        </div>
        <p className="text-sm">
          {formatLessonWhen(data.starts_at, data.duration_min, timeZone)}
          {note && <span className="text-muted-foreground">{` (${note})`}</span>}
        </p>
        <JoinButton url={data.join_url} />
      </div>
      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">Заметка репетитора</h2>
        {data.shared_note ? (
          <Markdown>{data.shared_note}</Markdown>
        ) : (
          <p className="text-sm text-muted-foreground">Заметки пока нет</p>
        )}
      </section>
    </>
  );
}
