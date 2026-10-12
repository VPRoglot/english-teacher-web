import type { LessonKind, LessonStatus } from "@/api/generated/model";

export const LESSON_STATUS_LABELS: Record<LessonStatus, string> = {
  scheduled: "Запланировано",
  completed: "Проведено",
  cancelled: "Отменено",
  cancelled_late: "Поздняя отмена",
  no_show: "Пропуск",
};

/** Занятие в статусе «Запланировано», которое уже началось: репетитору нужно его отметить. */
export const NEEDS_MARKING_LABEL = "Нужно отметить";

export function needsMarking(
  lesson: { status: LessonStatus; starts_at: string },
  now: Date,
): boolean {
  return lesson.status === "scheduled" && new Date(lesson.starts_at).getTime() <= now.getTime();
}

const MINUTE_MS = 60_000;

/** Конец занятия (мс с эпохи). */
export function lessonEndMs(lesson: { starts_at: string; duration_min: number }): number {
  return new Date(lesson.starts_at).getTime() + lesson.duration_min * MINUTE_MS;
}

/** К занятию ещё можно подключиться: оно запланировано и не закончилось (`now` — мс с эпохи). */
export function isJoinable(
  lesson: { status: LessonStatus; starts_at: string; duration_min: number },
  now: number,
): boolean {
  return lesson.status === "scheduled" && lessonEndMs(lesson) > now;
}

/** Коды дней недели в порядке RRULE и их подписи. */
export const WEEKDAYS: readonly (readonly [string, string])[] = [
  ["MO", "пн"],
  ["TU", "вт"],
  ["WE", "ср"],
  ["TH", "чт"],
  ["FR", "пт"],
  ["SA", "сб"],
  ["SU", "вс"],
];

const DAY_CODES = WEEKDAYS.map(([code]) => code);

/** Каноническая запись правила, как у backend: `FREQ=WEEKLY[;INTERVAL=n];BYDAY=…`, дни от MO к SU. */
export function buildRule({ days, interval }: { days: string[]; interval: 1 | 2 | 3 | 4 }): string {
  const ordered = [...new Set(days)].sort((a, b) => DAY_CODES.indexOf(a) - DAY_CODES.indexOf(b));
  const intervalPart = interval > 1 ? `;INTERVAL=${interval}` : "";
  return `FREQ=WEEKLY${intervalPart};BYDAY=${ordered.join(",")}`;
}

export function parseRule(rule: string): { days: string[]; interval: number } {
  const parts = new Map<string, string>();
  for (const part of rule.split(";")) {
    const [key, ...value] = part.split("=");
    if (key) parts.set(key.trim().toUpperCase(), value.join("=").trim());
  }
  const days = (parts.get("BYDAY") ?? "").split(",").filter((day) => day !== "");
  const interval = Number.parseInt(parts.get("INTERVAL") ?? "1", 10);
  return { days, interval: Number.isNaN(interval) ? 1 : interval };
}

const DAY_LABELS = new Map<string, string>(WEEKDAYS);

function joinDays(labels: string[]): string {
  if (labels.length <= 1) return labels.join("");
  return `${labels.slice(0, -1).join(", ")} и ${labels[labels.length - 1]}`;
}

/** `по вт и пт в 18:00, 60 мин` / `раз в 2 недели по пн в 10:00, 45 мин`. */
export function describeSeries(series: {
  rrule: string;
  local_start_time: string;
  duration_min: number;
}): string {
  const { days, interval } = parseRule(series.rrule);
  const labels = days.map((day) => DAY_LABELS.get(day) ?? day);
  const every = interval > 1 ? `раз в ${interval} недели ` : "";
  const time = series.local_start_time.slice(0, 5);
  return `${every}по ${joinDays(labels)} в ${time}, ${series.duration_min} мин`;
}

/**
 * CSS-класс цвета события календаря (стили — в `globals.css`).
 * Приоритет: нужно отметить, затем итоговые статусы, затем пробное, затем обычное запланированное.
 */
export function lessonEventClass(
  lesson: { status: LessonStatus; kind: LessonKind; starts_at: string },
  now: Date,
): string {
  if (needsMarking(lesson, now)) return "lesson-needs-marking";
  switch (lesson.status) {
    case "completed":
      return "lesson-completed";
    case "cancelled":
    case "cancelled_late":
      return "lesson-cancelled";
    case "no_show":
      return "lesson-no-show";
    case "scheduled":
      return lesson.kind === "trial" ? "lesson-trial" : "lesson-scheduled";
  }
}
