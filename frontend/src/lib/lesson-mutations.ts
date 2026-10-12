import type { QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import type { OverlapWarning } from "@/api/generated/model";

/** После создания или правки занятий и серий: списки занятий и серий устарели. */
export function invalidateSchedule(queryClient: QueryClient): void {
  void queryClient.invalidateQueries({ queryKey: ["/api/admin/lessons"] });
  void queryClient.invalidateQueries({ queryKey: ["/api/admin/series"] });
}

/** Каждое предупреждение о пересечении — отдельным уведомлением. */
export function toastWarnings(warnings: readonly OverlapWarning[]): void {
  for (const warning of warnings) toast.warning(warning.message);
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
