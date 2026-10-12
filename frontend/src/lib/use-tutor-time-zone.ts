"use client";

import { useGetTutorSettingsAdmin } from "@/api/generated/endpoints/admin/admin";
import { useGetScheduleSettings } from "@/api/generated/endpoints/cabinet/cabinet";

import { DEFAULT_TIME_ZONE } from "./datetime";

type Area = "admin" | "cabinet";

/**
 * Настройки репетитора: `/admin/settings` в админке и `/me/schedule-settings` в кабинете.
 * Запрос чужой области не выполняется: у семьи `/admin/settings` вернул бы 404.
 * Хуки с одним `area` делят один запрос (общий ключ react-query).
 */
function useTutorSettings(area: Area) {
  const admin = useGetTutorSettingsAdmin({ query: { enabled: area === "admin" } });
  const cabinet = useGetScheduleSettings({ query: { enabled: area === "cabinet" } });
  return area === "admin" ? admin.data : cabinet.data;
}

/**
 * Пояс репетитора. Пока настройки не загружены (или не загрузились) — `DEFAULT_TIME_ZONE`.
 */
export function useTutorTimeZone(area: Area): string {
  return useTutorSettings(area)?.timezone ?? DEFAULT_TIME_ZONE;
}

/**
 * `true`, когда настройки загружены и пояс из `useTutorTimeZone` настоящий, а не запасной.
 * Формы, которые переводят местное время в UTC, не отправляют данные, пока это не так.
 */
export function useTutorTimeZoneReady(area: Area): boolean {
  return useTutorSettings(area) !== undefined;
}
