"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { DateTime } from "luxon";
import { useMemo, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { useCreateSeries } from "@/api/generated/endpoints/admin/admin";
import type { SeriesDetail } from "@/api/generated/model";
import {
  LessonTimeFields,
  lessonTimeShape,
  meetingUrlShape,
} from "@/components/lesson-time-fields";
import { NATIVE_SELECT_CLASS } from "@/components/native-select";
import { TutorSettingsError } from "@/components/tutor-settings-error";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { todayInZone } from "@/lib/datetime";
import { applyApiErrors } from "@/lib/form-errors";
import { buildRule, parseRule, WEEKDAYS } from "@/lib/lesson-format";
import { invalidateSchedule, lessonsCount, toastWarnings } from "@/lib/lesson-mutations";
import { useTutorTimeZoneStatus } from "@/lib/use-tutor-time-zone";

const INTERVAL_LABELS: Record<string, string> = {
  "1": "каждую неделю",
  "2": "раз в 2 недели",
  "3": "раз в 3 недели",
  "4": "раз в 4 недели",
};

const FIELDS = ["time", "duration_min", "meeting_url", "starts_on", "ends_on", "from"] as const;

type Mode = "create" | "edit";

function makeSchema(mode: Mode) {
  return z
    .object({
      days: z.array(z.string()).min(1, "Выберите дни недели"),
      interval: z.enum(["1", "2", "3", "4"]),
      time: lessonTimeShape.time,
      duration_min: lessonTimeShape.duration_min,
      meeting_url: meetingUrlShape,
      starts_on: z.string(),
      ends_on: z.string(),
      from: z.string(),
    })
    .superRefine((values, ctx) => {
      const bound = mode === "create" ? values.starts_on : values.from;
      const boundField = mode === "create" ? "starts_on" : "from";
      if (!bound) {
        ctx.addIssue({ code: "custom", path: [boundField], message: "Укажите дату" });
      } else if (values.ends_on && values.ends_on < bound) {
        ctx.addIssue({
          code: "custom",
          path: ["ends_on"],
          message:
            mode === "create"
              ? "Окончание не может быть раньше начала"
              : "Окончание не может быть раньше даты изменения",
        });
      }
    });
}

type Values = z.infer<ReturnType<typeof makeSchema>>;

/** Что собрала форма в режиме правки; отправку (`PATCH /admin/series/{id}`) подключает вызывающий. */
export type SeriesEditValues = {
  from: string;
  rrule: string;
  local_start_time: string;
  duration_min: number;
  meeting_url: string | null;
  ends_on: string | null;
};

export type SeriesFormProps = {
  mode: Mode;
  /** Ребёнок, которому создаётся серия; `null`, пока ученик не выбран (см. `onChildMissing`). */
  childId?: string | null;
  /** Правка: текущие значения серии. */
  series?: SeriesDetail;
  /** Создание: местные день и время клика — из них предзаполняются день недели, время и «Начало». */
  initial?: { date: string; time: string };
  onSaved?: () => void;
  /**
   * Правка: отправляет вызывающий. Ожидается `Promise`: пока он выполняется, кнопка недоступна;
   * успех закрывает форму (`onSaved`), `ApiError` ложится на поля (422) или в общую ошибку формы.
   */
  onEditSubmit?: (values: SeriesEditValues) => Promise<unknown> | void;
  /** Вызывается вместо отправки, если `childId` не задан. */
  onChildMissing?: () => void;
};

function weekdayCode(date: string): string | null {
  const day = DateTime.fromISO(date).weekday;
  return WEEKDAYS[day - 1]?.[0] ?? null;
}

function toInterval(value: string): 1 | 2 | 3 | 4 {
  return Number(value) as 1 | 2 | 3 | 4;
}

function defaultValues(
  mode: Mode,
  series: SeriesDetail | undefined,
  initial: { date: string; time: string } | undefined,
  today: string,
): Values {
  if (mode === "edit" && series) {
    const { days, interval } = parseRule(series.rrule);
    return {
      days,
      interval: String(Math.min(Math.max(interval, 1), 4)) as Values["interval"],
      time: series.local_start_time.slice(0, 5),
      duration_min: series.duration_min,
      meeting_url: series.meeting_url ?? "",
      starts_on: series.starts_on,
      ends_on: series.ends_on ?? "",
      from: today,
    };
  }
  const day = initial ? weekdayCode(initial.date) : null;
  return {
    days: day ? [day] : [],
    interval: "1",
    time: initial?.time ?? "",
    duration_min: 60,
    meeting_url: "",
    starts_on: initial?.date ?? today,
    ends_on: "",
    from: today,
  };
}

/**
 * Форма регулярного расписания: создание (`POST /admin/series`) или поля для правки.
 * Пока пояс репетитора не загружен, отправка заблокирована; форма пересоздаётся, когда пояс
 * появился, чтобы даты по умолчанию («Начало», «Изменить начиная с») считались в настоящем поясе.
 */
export function SeriesForm(props: SeriesFormProps) {
  const { timeZone, ready, error } = useTutorTimeZoneStatus("admin");
  if (error) return <TutorSettingsError />;
  return (
    <SeriesFormBody key={`${ready}:${timeZone}`} {...props} timeZone={timeZone} ready={ready} />
  );
}

function SeriesFormBody({
  mode,
  childId = null,
  series,
  initial,
  onSaved,
  onEditSubmit,
  onChildMissing,
  timeZone,
  ready,
}: SeriesFormProps & { timeZone: string; ready: boolean }) {
  const queryClient = useQueryClient();
  const createSeries = useCreateSeries();
  const [editPending, setEditPending] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const schema = useMemo(() => makeSchema(mode), [mode]);
  const idPrefix = `series-${series?.id ?? "new"}`;
  const pending = createSeries.isPending || editPending;

  const {
    register,
    control,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: defaultValues(mode, series, initial, todayInZone(timeZone)),
  });

  async function submitEdit(values: SeriesEditValues) {
    setEditPending(true);
    try {
      await onEditSubmit?.(values);
      onSaved?.();
    } catch (error) {
      setFormError(applyApiErrors(error, setError, FIELDS));
    } finally {
      setEditPending(false);
    }
  }

  function onSubmit(values: Values) {
    setFormError(null);
    const rrule = buildRule({ days: values.days, interval: toInterval(values.interval) });
    const localStartTime = values.time.slice(0, 5);

    if (mode === "edit") {
      void submitEdit({
        from: values.from,
        rrule,
        local_start_time: localStartTime,
        duration_min: values.duration_min,
        meeting_url: values.meeting_url || null,
        ends_on: values.ends_on || null,
      });
      return;
    }

    if (!childId) {
      onChildMissing?.();
      return;
    }
    createSeries.mutate(
      {
        data: {
          child_id: childId,
          rrule,
          local_start_time: localStartTime,
          duration_min: values.duration_min,
          starts_on: values.starts_on,
          ...(values.meeting_url ? { meeting_url: values.meeting_url } : {}),
          ...(values.ends_on ? { ends_on: values.ends_on } : {}),
        },
      },
      {
        onSuccess: (saved) => {
          toast.success(`Расписание создано: ${lessonsCount(saved.lessons_created)}`);
          toastWarnings(saved.warnings);
          invalidateSchedule(queryClient);
          onSaved?.();
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
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-2 text-sm font-medium">Дни недели</legend>
        <Controller
          name="days"
          control={control}
          render={({ field }) => (
            <div className="flex flex-wrap gap-x-4 gap-y-2">
              {WEEKDAYS.map(([code, label]) => (
                <div key={code} className="flex items-center gap-2">
                  <Checkbox
                    id={`${idPrefix}-day-${code}`}
                    checked={field.value.includes(code)}
                    onCheckedChange={(checked) =>
                      field.onChange(
                        checked ? [...field.value, code] : field.value.filter((d) => d !== code),
                      )
                    }
                  />
                  <Label htmlFor={`${idPrefix}-day-${code}`} className="font-normal">
                    {label}
                  </Label>
                </div>
              ))}
            </div>
          )}
        />
        {errors.days && <p className="text-sm text-destructive">{errors.days.message}</p>}
      </fieldset>
      <div className="flex flex-col gap-2">
        <Label htmlFor={`${idPrefix}-interval`}>Повтор</Label>
        <select id={`${idPrefix}-interval`} className={NATIVE_SELECT_CLASS} {...register("interval")}>
          {Object.entries(INTERVAL_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>
      <LessonTimeFields register={register} errors={errors} idPrefix={idPrefix} withDate={false} />
      <div className="flex flex-col gap-2">
        <Label htmlFor={`${idPrefix}-url`}>Ссылка на занятие</Label>
        <Input
          id={`${idPrefix}-url`}
          type="url"
          placeholder="https://"
          aria-invalid={errors.meeting_url ? true : undefined}
          {...register("meeting_url")}
        />
        {errors.meeting_url && (
          <p className="text-sm text-destructive">{errors.meeting_url.message}</p>
        )}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {mode === "create" ? (
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${idPrefix}-starts`}>Начало</Label>
            <Input
              id={`${idPrefix}-starts`}
              type="date"
              aria-invalid={errors.starts_on ? true : undefined}
              {...register("starts_on")}
            />
            {errors.starts_on && (
              <p className="text-sm text-destructive">{errors.starts_on.message}</p>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${idPrefix}-from`}>Изменить начиная с</Label>
            <Input
              id={`${idPrefix}-from`}
              type="date"
              aria-invalid={errors.from ? true : undefined}
              {...register("from")}
            />
            {errors.from && (
              <p className="text-sm text-destructive">{errors.from.message}</p>
            )}
          </div>
        )}
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${idPrefix}-ends`}>Окончание</Label>
          <Input
            id={`${idPrefix}-ends`}
            type="date"
            aria-invalid={errors.ends_on ? true : undefined}
            {...register("ends_on")}
          />
          {errors.ends_on && <p className="text-sm text-destructive">{errors.ends_on.message}</p>}
        </div>
      </div>
      <Button type="submit" disabled={pending || !ready}>
        {pending ? "Сохраняем…" : mode === "create" ? "Создать" : "Сохранить"}
      </Button>
    </form>
  );
}

export type SeriesFormDialogProps = SeriesFormProps & {
  /** Управляемое открытие. Без него диалог сам рисует кнопку-триггер и держит состояние. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
};

/** Диалог регулярного расписания: «Добавить расписание» (`create`) или «Изменить» (`edit`). */
export function SeriesFormDialog({
  open,
  onOpenChange,
  onSaved,
  ...formProps
}: SeriesFormDialogProps) {
  const [ownOpen, setOwnOpen] = useState(false);
  const controlled = open !== undefined;
  const isOpen = controlled ? open : ownOpen;
  const setOpen = controlled ? (onOpenChange ?? (() => {})) : setOwnOpen;
  const create = formProps.mode === "create";

  return (
    <>
      {!controlled && (
        <Button
          type="button"
          variant="outline"
          size={create ? "default" : "sm"}
          onClick={() => setOwnOpen(true)}
        >
          {create ? "Добавить расписание" : "Изменить"}
        </Button>
      )}
      <Dialog open={isOpen} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{create ? "Новое расписание" : "Изменить расписание"}</DialogTitle>
          </DialogHeader>
          <SeriesForm
            {...formProps}
            onSaved={() => {
              setOpen(false);
              onSaved?.();
            }}
          />
        </DialogContent>
      </Dialog>
    </>
  );
}
