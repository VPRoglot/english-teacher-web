import type { ChangeRequestStatus, ChangeRequestType } from "@/api/generated/model";

export const CHANGE_REQUEST_TYPE_LABELS: Record<ChangeRequestType, string> = {
  reschedule: "Перенос",
  cancel: "Отмена",
};

export const CHANGE_REQUEST_STATUS_LABELS: Record<ChangeRequestStatus, string> = {
  pending: "Ждёт ответа репетитора",
  approved: "Одобрен",
  rejected: "Отклонён",
  withdrawn: "Отозван",
};

const HOUR_MS = 3_600_000;

/**
 * До начала занятия осталось меньше `policyHours` часов (граница, как на backend, строгая:
 * ровно `policyHours` — ещё не поздно). Порог 0 — никогда не поздно.
 */
export function isLateNow(startsAt: string, policyHours: number, now: Date): boolean {
  if (policyHours <= 0) return false;
  return new Date(startsAt).getTime() - now.getTime() < policyHours * HOUR_MS;
}
