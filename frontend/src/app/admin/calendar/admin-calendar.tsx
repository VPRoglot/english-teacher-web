"use client";

import type { EventInput } from "@fullcalendar/core";
import { keepPreviousData } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useListLessons } from "@/api/generated/endpoints/admin/admin";
import type { AdminLessonItem } from "@/api/generated/model";
import { LessonCalendar } from "@/components/lesson-calendar";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { nextHourParts, utcToZonedParts } from "@/lib/datetime";
import { errorMessage } from "@/lib/form-errors";
import { lessonEventClass } from "@/lib/lesson-format";
import { useTutorTimeZone } from "@/lib/use-tutor-time-zone";

import { CreateLessonDialog } from "./create-lesson-dialog";

const VIEWS = { desktop: ["timeGridWeek", "timeGridDay"], mobile: "listWeek" };
const CLOCK_TICK_MS = 60_000;

/** Занятия → события календаря: заголовок — ученик (у пробного «Пробное: …»), цвет — по статусу. */
export function toAdminEvents(lessons: AdminLessonItem[], now: Date): EventInput[] {
  return lessons.map((lesson) => ({
    id: lesson.id,
    title: lesson.kind === "trial" ? `Пробное: ${lesson.student.name}` : lesson.student.name,
    start: lesson.starts_at,
    end: new Date(new Date(lesson.starts_at).getTime() + lesson.duration_min * 60_000).toISOString(),
    classNames: [lessonEventClass(lesson, now)],
  }));
}

type Range = { from: string; to: string };

/** Текущее время для окраски «нужно отметить»: обновляется раз в минуту. */
function useNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), CLOCK_TICK_MS);
    return () => clearInterval(timer);
  }, []);
  return now;
}

export function AdminCalendar() {
  const router = useRouter();
  const timeZone = useTutorTimeZone("admin");
  const now = useNow();
  const [range, setRange] = useState<Range | null>(null);
  const [dialog, setDialog] = useState<{ open: boolean; initial: { date: string; time: string } }>(
    { open: false, initial: { date: "", time: "" } },
  );

  const lessons = useListLessons(range ?? { from: "", to: "" }, {
    query: { enabled: range !== null, placeholderData: keepPreviousData },
  });
  const events = useMemo(() => toAdminEvents(lessons.data ?? [], now), [lessons.data, now]);

  function openDialog(initial: { date: string; time: string }) {
    setDialog({ open: true, initial });
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">Календарь</h1>
        <Button type="button" onClick={() => openDialog(nextHourParts(timeZone))}>
          Добавить занятие
        </Button>
      </div>
      {lessons.error && (
        <Alert variant="destructive">
          <AlertDescription>{errorMessage(lessons.error)}</AlertDescription>
        </Alert>
      )}
      <LessonCalendar
        events={events}
        timeZone={timeZone}
        views={VIEWS}
        onRangeChange={(start, end) => {
          const next = { from: start.toISOString(), to: end.toISOString() };
          setRange((current) =>
            current?.from === next.from && current.to === next.to ? current : next,
          );
        }}
        onEventClick={(id) => router.push(`/admin/lessons/${id}`)}
        onSlotClick={(date) => openDialog(utcToZonedParts(date.toISOString(), timeZone))}
      />
      <CreateLessonDialog
        open={dialog.open}
        onOpenChange={(open) => setDialog((current) => ({ ...current, open }))}
        initial={dialog.initial}
      />
    </div>
  );
}
