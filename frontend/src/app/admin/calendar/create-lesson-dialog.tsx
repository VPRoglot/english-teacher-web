"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { useCreateLesson, useListFamilies } from "@/api/generated/endpoints/admin/admin";
import {
  LessonTimeFields,
  lessonTimeShape,
  meetingUrlShape,
} from "@/components/lesson-time-fields";
import { NATIVE_SELECT_CLASS } from "@/components/native-select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { zonedToUtcIso } from "@/lib/datetime";
import { applyApiErrors, errorMessage } from "@/lib/form-errors";
import { invalidateSchedule, toastWarnings } from "@/lib/lesson-mutations";
import { useTutorTimeZone } from "@/lib/use-tutor-time-zone";

import { SeriesForm } from "../series-form-dialog";

const schema = z.object({
  date: lessonTimeShape.date,
  time: lessonTimeShape.time,
  duration_min: lessonTimeShape.duration_min,
  meeting_url: meetingUrlShape,
});

type Values = z.infer<typeof schema>;

const FIELDS = ["duration_min", "meeting_url"] as const;
const NO_STUDENT_MESSAGE = "Выберите ученика";

type Slot = { date: string; time: string };

function OneOffForm({
  childId,
  initial,
  onChildMissing,
  onSaved,
}: {
  childId: string;
  initial: Slot;
  onChildMissing: () => void;
  onSaved: () => void;
}) {
  const queryClient = useQueryClient();
  const timeZone = useTutorTimeZone("admin");
  const createLesson = useCreateLesson();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { date: initial.date, time: initial.time, duration_min: 60, meeting_url: "" },
  });

  function onSubmit(values: Values) {
    setFormError(null);
    if (!childId) {
      onChildMissing();
      return;
    }
    let startsAt: string;
    try {
      startsAt = zonedToUtcIso(values.date, values.time, timeZone);
    } catch (error) {
      setFormError(errorMessage(error));
      return;
    }
    createLesson.mutate(
      {
        data: {
          child_id: childId,
          starts_at: startsAt,
          duration_min: values.duration_min,
          ...(values.meeting_url ? { meeting_url: values.meeting_url } : {}),
        },
      },
      {
        onSuccess: (saved) => {
          toast.success("Занятие создано");
          toastWarnings(saved.warnings);
          invalidateSchedule(queryClient);
          onSaved();
        },
        onError: (error) => setFormError(applyApiErrors(error, setError, FIELDS)),
      },
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
      {formError && (
        <Alert variant="destructive">
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      )}
      <LessonTimeFields register={register} errors={errors} idPrefix="lesson-new" />
      <div className="flex flex-col gap-2">
        <Label htmlFor="lesson-new-url">Ссылка на занятие</Label>
        <Input
          id="lesson-new-url"
          type="url"
          placeholder="https://"
          aria-invalid={errors.meeting_url ? true : undefined}
          {...register("meeting_url")}
        />
        {errors.meeting_url && (
          <p className="text-sm text-destructive">{errors.meeting_url.message}</p>
        )}
      </div>
      <Button type="submit" disabled={createLesson.isPending}>
        {createLesson.isPending ? "Сохраняем…" : "Создать"}
      </Button>
    </form>
  );
}

/** Ученик: «Семья — ребёнок» из активных детей. */
function StudentSelect({
  value,
  onChange,
  error,
}: {
  value: string;
  onChange: (childId: string) => void;
  error: string | null;
}) {
  const families = useListFamilies();
  const options = useMemo(
    () =>
      (families.data ?? []).flatMap((family) =>
        family.children.map((child) => ({
          id: child.id,
          label: `${family.name} — ${child.full_name}`,
        })),
      ),
    [families.data],
  );
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor="lesson-new-student">Ученик</Label>
      <select
        id="lesson-new-student"
        className={NATIVE_SELECT_CLASS}
        aria-invalid={error ? true : undefined}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">Выберите ученика</option>
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </select>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {families.error && <p className="text-sm text-destructive">{errorMessage(families.error)}</p>}
      {families.data && options.length === 0 && (
        <p className="text-sm text-muted-foreground">Пока нет учеников: сначала добавьте семью.</p>
      )}
    </div>
  );
}

function CreateLessonForm({ initial, onClose }: { initial: Slot; onClose: () => void }) {
  const [regular, setRegular] = useState(false);
  const [childId, setChildId] = useState("");
  const [childError, setChildError] = useState<string | null>(null);
  const onChildMissing = () => setChildError(NO_STUDENT_MESSAGE);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          variant={regular ? "outline" : "default"}
          aria-pressed={!regular}
          onClick={() => setRegular(false)}
        >
          Разовое
        </Button>
        <Button
          type="button"
          size="sm"
          variant={regular ? "default" : "outline"}
          aria-pressed={regular}
          onClick={() => setRegular(true)}
        >
          Регулярное
        </Button>
      </div>
      <StudentSelect
        value={childId}
        error={childError}
        onChange={(value) => {
          setChildId(value);
          setChildError(null);
        }}
      />
      {regular ? (
        <SeriesForm
          mode="create"
          childId={childId}
          initial={initial}
          onChildMissing={onChildMissing}
          onSaved={onClose}
        />
      ) : (
        <OneOffForm
          childId={childId}
          initial={initial}
          onChildMissing={onChildMissing}
          onSaved={onClose}
        />
      )}
    </div>
  );
}

/**
 * «Добавить занятие»: разовое (`POST /admin/lessons`) или регулярное (`POST /admin/series`).
 * `initial` — местные дата и время в поясе репетитора.
 */
export function CreateLessonDialog({
  open,
  onOpenChange,
  initial,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initial: Slot;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Новое занятие</DialogTitle>
        </DialogHeader>
        <CreateLessonForm initial={initial} onClose={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}
