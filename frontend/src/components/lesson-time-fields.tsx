"use client";

import type { FieldErrors, FieldValues, UseFormRegister } from "react-hook-form";
import { z } from "zod";

import {
  createLessonBodyDurationMinMax,
  createLessonBodyDurationMinMin,
} from "@/api/generated/zod/admin/admin";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export const DURATION_STEP_MIN = 5;

/** Поля формы, которые читает и пишет `LessonTimeFields`. Дата не нужна, если `withDate={false}`. */
export type LessonTimeValues = { date: string; time: string; duration_min: number };

/** Куски zod-схемы для форм со временем занятия; значения — местные в поясе репетитора. */
export const lessonTimeShape = {
  date: z.string().min(1, "Укажите дату"),
  time: z.string().min(1, "Укажите время"),
  duration_min: z
    .number("Введите длительность")
    .int("Введите целое число минут")
    .min(createLessonBodyDurationMinMin, `Не менее ${createLessonBodyDurationMinMin} минут`)
    .max(createLessonBodyDurationMinMax, `Не более ${createLessonBodyDurationMinMax} минут`),
};

/** Необязательная ссылка на занятие: пустая строка допустима, иначе корректный URL. */
export const meetingUrlShape = z
  .string()
  .trim()
  .max(2083, "Не более 2083 символов")
  .refine((value) => value === "" || z.url().safeParse(value).success, "Введите корректную ссылку");

type Props<T extends FieldValues> = {
  register: UseFormRegister<T>;
  errors: FieldErrors<T>;
  /** Префикс `id` полей: в одной странице может быть несколько форм. */
  idPrefix: string;
  /** Показывать «Дату»; у регулярной серии даты свои («Начало», «Окончание»). */
  withDate?: boolean;
};

function FieldError({ message }: { message?: string }) {
  return message ? <p className="text-sm text-destructive">{message}</p> : null;
}

/**
 * «Дата», «Время» (шаг 5 минут) и «Длительность, мин» для react-hook-form.
 * Значения — местные дата и время в поясе репетитора; в UTC их переводит вызывающий (`zonedToUtcIso`).
 * Форма должна иметь поля `date` (если `withDate`), `time` и `duration_min` (число).
 */
export function LessonTimeFields<T extends FieldValues>({
  register,
  errors,
  idPrefix,
  withDate = true,
}: Props<T>) {
  const fields = register as unknown as UseFormRegister<LessonTimeValues>;
  const issues = errors as FieldErrors<LessonTimeValues>;
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {withDate && (
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${idPrefix}-date`}>Дата</Label>
          <Input
            id={`${idPrefix}-date`}
            type="date"
            aria-invalid={issues.date ? true : undefined}
            {...fields("date")}
          />
          <FieldError message={issues.date?.message} />
        </div>
      )}
      <div className="flex flex-col gap-2">
        <Label htmlFor={`${idPrefix}-time`}>Время</Label>
        <Input
          id={`${idPrefix}-time`}
          type="time"
          step={DURATION_STEP_MIN * 60}
          aria-invalid={issues.time ? true : undefined}
          {...fields("time")}
        />
        <FieldError message={issues.time?.message} />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor={`${idPrefix}-duration`}>Длительность, мин</Label>
        <Input
          id={`${idPrefix}-duration`}
          type="number"
          inputMode="numeric"
          min={createLessonBodyDurationMinMin}
          max={createLessonBodyDurationMinMax}
          step={DURATION_STEP_MIN}
          aria-invalid={issues.duration_min ? true : undefined}
          {...fields("duration_min", { valueAsNumber: true })}
        />
        <FieldError message={issues.duration_min?.message} />
      </div>
    </div>
  );
}
