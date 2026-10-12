"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";

import {
  getGetLessonQueryKey,
  useDeleteLesson,
  useGetLesson,
  useSaveLessonNotes,
} from "@/api/generated/endpoints/admin/admin";
import type { AdminLessonDetail } from "@/api/generated/model";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { MarkdownEditor } from "@/components/markdown-editor";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatLessonWhen, timeZoneNote } from "@/lib/datetime";
import { errorMessage } from "@/lib/form-errors";
import { LESSON_STATUS_LABELS, NEEDS_MARKING_LABEL, needsMarking } from "@/lib/lesson-format";
import { invalidateSchedule } from "@/lib/lesson-mutations";
import { useTutorTimeZone } from "@/lib/use-tutor-time-zone";

import { EditLessonDialog } from "./edit-lesson-dialog";
import { LessonStatusSelect } from "./lesson-status-select";

const NOTE_MAX_LENGTH = 20000;
const CLOCK_TICK_MS = 30_000;

/** Текущее время для «будущее/прошедшее» и «Нужно отметить»; обновляется, пока страница открыта. */
function useNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), CLOCK_TICK_MS);
    return () => clearInterval(timer);
  }, []);
  return now;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}

function StudentLink({ lesson }: { lesson: AdminLessonDetail }) {
  const { student } = lesson;
  const href = student.family_id
    ? `/admin/families/${student.family_id}`
    : student.lead_id
      ? `/admin/leads/${student.lead_id}`
      : null;
  return (
    <>
      {href ? (
        <Link href={href} className="underline underline-offset-2">
          {student.name}
        </Link>
      ) : (
        student.name
      )}
    </>
  );
}

function LessonFields({ lesson }: { lesson: AdminLessonDetail }) {
  const timeZone = useTutorTimeZone("admin");
  const note = timeZoneNote(timeZone);
  return (
    <dl className="grid gap-4 sm:grid-cols-2">
      <Field label="Ученик">
        <StudentLink lesson={lesson} />
      </Field>
      {lesson.student.family_name && <Field label="Семья">{lesson.student.family_name}</Field>}
      <Field label="Время">
        {formatLessonWhen(lesson.starts_at, lesson.duration_min, timeZone)}
        {note && <span className="text-muted-foreground">{` (${note})`}</span>}
      </Field>
      <Field label="Длительность">{`${lesson.duration_min} мин`}</Field>
      <Field label="Ссылка">
        {lesson.join_url ? (
          <a
            href={lesson.join_url}
            target="_blank"
            rel="noopener noreferrer"
            className="underline underline-offset-2"
          >
            Подключиться
          </a>
        ) : (
          <span className="text-muted-foreground">Не указана</span>
        )}
      </Field>
    </dl>
  );
}

function LessonNotes({ lesson }: { lesson: AdminLessonDetail }) {
  const queryClient = useQueryClient();
  const save = useSaveLessonNotes();
  const [shared, setShared] = useState(lesson.notes.shared_text);
  const [priv, setPriv] = useState(lesson.notes.private_text);
  const [error, setError] = useState<string | null>(null);
  const dirty = shared !== lesson.notes.shared_text || priv !== lesson.notes.private_text;

  // Уход со страницы (закрытие вкладки, обновление) с несохранённой заметкой.
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  function submit() {
    setError(null);
    save.mutate(
      { lessonId: lesson.id, data: { shared_text: shared, private_text: priv } },
      {
        onSuccess: (notes) => {
          toast.success("Заметка сохранена");
          // Сохранённое становится новой «чистой» точкой отсчёта без повторной загрузки занятия.
          queryClient.setQueryData<AdminLessonDetail>(getGetLessonQueryKey(lesson.id), (old) =>
            old
              ? { ...old, notes, has_notes: notes.shared_text !== "" || notes.private_text !== "" }
              : old,
          );
          invalidateSchedule(queryClient);
        },
        onError: (e) => setError(errorMessage(e)),
      },
    );
  }

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold">Заметка</h2>
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <MarkdownEditor
        label="Общая — видна семье"
        description="Родители видят этот текст в кабинете."
        value={shared}
        onChange={setShared}
        maxLength={NOTE_MAX_LENGTH}
      />
      <MarkdownEditor
        label="Приватная — только для вас"
        description="Семье не показывается."
        value={priv}
        onChange={setPriv}
        maxLength={NOTE_MAX_LENGTH}
      />
      <Button
        type="button"
        className="self-start"
        disabled={!dirty || save.isPending}
        onClick={submit}
      >
        Сохранить заметку
      </Button>
    </section>
  );
}

function DeleteLesson({ lesson }: { lesson: AdminLessonDetail }) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const remove = useDeleteLesson();
  const [open, setOpen] = useState(false);

  async function confirm() {
    await remove.mutateAsync({ lessonId: lesson.id });
    toast.success("Занятие удалено");
    queryClient.removeQueries({ queryKey: getGetLessonQueryKey(lesson.id) });
    invalidateSchedule(queryClient);
    router.push("/admin/calendar");
  }

  return (
    <>
      <Button type="button" variant="destructive" onClick={() => setOpen(true)}>
        Удалить
      </Button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Удалить занятие?"
        description="Занятие исчезнет из расписания. Это действие нельзя отменить."
        confirmLabel="Удалить"
        onConfirm={confirm}
      />
    </>
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

export function LessonDetail() {
  const { id } = useParams<{ id: string }>();
  const lesson = useGetLesson(id);
  const now = useNow();
  const [editing, setEditing] = useState(false);

  if (lesson.error && !lesson.data) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p className="text-sm text-muted-foreground">{errorMessage(lesson.error)}</p>
        <Link href="/admin/calendar" className="text-sm underline underline-offset-2">
          К календарю
        </Link>
      </div>
    );
  }
  if (!lesson.data) return <Skeleton />;

  const data = lesson.data;
  const future = new Date(data.starts_at).getTime() > now.getTime();
  const scheduled = data.status === "scheduled";

  return (
    <>
      <div className="flex flex-col gap-3">
        <Link href="/admin/calendar" className="text-sm text-muted-foreground hover:text-foreground">
          К календарю
        </Link>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">{data.student.name}</h1>
          <Badge variant="secondary">{LESSON_STATUS_LABELS[data.status]}</Badge>
          {needsMarking(data, now) && <Badge variant="destructive">{NEEDS_MARKING_LABEL}</Badge>}
          {data.kind === "trial" && <Badge variant="outline">Пробное</Badge>}
          {data.series_id && <Badge variant="outline">Из расписания</Badge>}
          {data.is_detached && <Badge variant="outline">Перенесено</Badge>}
        </div>
      </div>
      <LessonFields lesson={data} />
      <section className="flex flex-col gap-4">
        <LessonStatusSelect lesson={data} now={now} />
        {scheduled && (
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={() => setEditing(true)}>
              Перенести
            </Button>
            {future && <DeleteLesson lesson={data} />}
          </div>
        )}
      </section>
      <LessonNotes lesson={data} />
      {scheduled && <EditLessonDialog lesson={data} open={editing} onOpenChange={setEditing} />}
    </>
  );
}
