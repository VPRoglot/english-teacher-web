"use client";

import { useGetTutorSettingsAdmin } from "@/api/generated/endpoints/admin/admin";
import { useGetScheduleSettings } from "@/api/generated/endpoints/cabinet/cabinet";

import { DEFAULT_TIME_ZONE } from "./datetime";

/**
 * Пояс репетитора: из `/admin/settings` в админке и из `/me/schedule-settings` в кабинете.
 * Пока настройки не загружены (или не загрузились) — `DEFAULT_TIME_ZONE`.
 * Запрос чужой области не выполняется: у семьи `/admin/settings` вернул бы 404.
 */
export function useTutorTimeZone(area: "admin" | "cabinet"): string {
  const admin = useGetTutorSettingsAdmin({ query: { enabled: area === "admin" } });
  const cabinet = useGetScheduleSettings({ query: { enabled: area === "cabinet" } });
  const settings = area === "admin" ? admin.data : cabinet.data;
  return settings?.timezone ?? DEFAULT_TIME_ZONE;
}
