"use client";

import type { EventInput } from "@fullcalendar/core";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { useGetMe } from "@/api/generated/endpoints/auth/auth";
import { useListMyLessons } from "@/api/generated/endpoints/cabinet/cabinet";
import type { LessonForFamily } from "@/api/generated/model";
import { LessonCalendar } from "@/components/lesson-calendar";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { errorMessage } from "@/lib/form-errors";
import { lessonEventClass } from "@/lib/lesson-format";
import { useTutorTimeZone } from "@/lib/use-tutor-time-zone";

import { withChild } from "../child-link";
import { useSelectedChild } from "../use-selected-child";

const VIEWS = { desktop: ["dayGridMonth", "timeGridWeek"], mobile: "listMonth" };
const GENERIC_TITLE = "Английский";
const EMPTY_TEXT = "Занятий нет";

// Семья не видит служебной раскраски «нужно отметить»: для неё незавершённое прошедшее занятие
// остаётся «запланированным». Момент в далёком прошлом исключает эту ветку, а итоговые статусы
// от момента не зависят.
const NEVER_STARTED = new Date(0);

/** Занятия → события календаря: заголовок — имя ребёнка (если детей несколько) или «Английский». */
export function toCabinetEvents(
  lessons: LessonForFamily[],
  { showChildName }: { showChildName: boolean },
): EventInput[] {
  return lessons.map((lesson) => ({
    id: lesson.id,
    title: showChildName ? lesson.child_name : GENERIC_TITLE,
    start: lesson.starts_at,
    end: new Date(new Date(lesson.starts_at).getTime() + lesson.duration_min * 60_000).toISOString(),
    classNames: [lessonEventClass({ ...lesson, kind: "regular" }, NEVER_STARTED)],
  }));
}

type Range = { from: string; to: string };

/** `child_id` из ключа запроса `[url, params]`; без него — `null` («все дети»). */
function keyChildId(queryKey: readonly unknown[] | undefined): string | null {
  const params = queryKey?.[1] as { child_id?: string } | undefined;
  return params?.child_id ?? null;
}

export function CabinetCalendar() {
  const router = useRouter();
  const me = useGetMe();
  const timeZone = useTutorTimeZone("cabinet");
  const { childId } = useSelectedChild();
  const [range, setRange] = useState<Range | null>(null);

  const params = {
    from: range?.from ?? "",
    to: range?.to ?? "",
    ...(childId ? { child_id: childId } : {}),
  };
  const lessons = useListMyLessons(params, {
    query: {
      enabled: range !== null,
      // Соседний диапазон того же ребёнка держим на экране, пока грузится новый; чужого ребёнка — нет.
      placeholderData: (previous, previousQuery) =>
        keyChildId(previousQuery?.queryKey) === childId ? previous : undefined,
    },
  });

  const showChildName = (me.data?.children.length ?? 0) > 1;
  const events = useMemo(
    () => toCabinetEvents(lessons.data ?? [], { showChildName }),
    [lessons.data, showChildName],
  );

  function openLesson(id: string) {
    router.push(withChild(`/cabinet/lessons/${id}`, childId));
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Календарь</h1>
      {lessons.error && (
        <Alert variant="destructive">
          <AlertDescription>{errorMessage(lessons.error)}</AlertDescription>
        </Alert>
      )}
      <LessonCalendar
        events={events}
        timeZone={timeZone}
        views={VIEWS}
        emptyText={EMPTY_TEXT}
        onRangeChange={(start, end) => {
          const next = { from: start.toISOString(), to: end.toISOString() };
          setRange((current) =>
            current?.from === next.from && current.to === next.to ? current : next,
          );
        }}
        onEventClick={openLesson}
      />
    </div>
  );
}
