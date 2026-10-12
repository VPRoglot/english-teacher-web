import type { QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import type { OverlapWarning } from "@/api/generated/model";

const SCHEDULE_PREFIXES = ["/api/admin/lessons", "/api/admin/series"];
const LEAD_PREFIX = "/api/admin/leads/";
const TRIAL_LESSONS_SUFFIX = "/trial-lessons";

/**
 * Запрос относится к расписанию: списки и карточки занятий (`/api/admin/lessons…`), серии
 * (`/api/admin/series…`) и пробные занятия заявок (`/api/admin/leads/{id}/trial-lessons`).
 * Ключи orval — строка пути первым элементом, поэтому проверяется только он.
 */
export function isScheduleQueryKey(queryKey: readonly unknown[]): boolean {
  const path = queryKey[0];
  if (typeof path !== "string") return false;
  if (SCHEDULE_PREFIXES.some((prefix) => path.startsWith(prefix))) return true;
  return path.startsWith(LEAD_PREFIX) && path.endsWith(TRIAL_LESSONS_SUFFIX);
}

/** После создания, правки занятий и серий или смены пояса: всё расписание устарело. */
export function invalidateSchedule(queryClient: QueryClient): void {
  void queryClient.invalidateQueries({ predicate: ({ queryKey }) => isScheduleQueryKey(queryKey) });
}

/** Каждое предупреждение о пересечении — отдельным уведомлением. */
export function toastWarnings(warnings: readonly OverlapWarning[]): void {
  for (const warning of warnings) toast.warning(warning.message);
}

/**
 * Сообщение после правки серии: `Расписание изменено: обновлено 6 занятий, добавлено 2,
 * удалено 1`. Нулевые части опускаются; существительное — только у первой части.
 */
export function seriesEditedMessage(counts: {
  updated: number;
  created: number;
  removed: number;
}): string {
  const parts = (
    [
      ["обновлено", counts.updated],
      ["добавлено", counts.created],
      ["удалено", counts.removed],
    ] as const
  ).filter(([, count]) => count > 0);
  if (parts.length === 0) return "Расписание изменено";
  const text = parts
    .map(([verb, count], index) => `${verb} ${index === 0 ? lessonsCount(count) : count}`)
    .join(", ");
  return `Расписание изменено: ${text}`;
}

/** `1 занятие`, `3 занятия`, `16 занятий`. */
export function lessonsCount(count: number): string {
  const tens = count % 100;
  const units = count % 10;
  if (tens >= 11 && tens <= 14) return `${count} занятий`;
  if (units === 1) return `${count} занятие`;
  if (units >= 2 && units <= 4) return `${count} занятия`;
  return `${count} занятий`;
}
