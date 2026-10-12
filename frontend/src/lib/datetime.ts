import { DateTime } from "luxon";

/** Пояс репетитора, пока настройки не загружены (и значение по умолчанию на backend). */
export const DEFAULT_TIME_ZONE = "Europe/Moscow";

function inZone(iso: string, tz: string): DateTime {
  return DateTime.fromISO(iso, { zone: tz, locale: "ru" });
}

/** `dd.MM.yyyy HH:mm` в поясе `tz`. */
export function formatDateTime(iso: string, tz: string): string {
  return inZone(iso, tz).toFormat("dd.MM.yyyy HH:mm");
}

/** `dd.MM.yyyy` в поясе `tz`. */
export function formatDate(iso: string, tz: string): string {
  return inZone(iso, tz).toFormat("dd.MM.yyyy");
}

/** `HH:mm` в поясе `tz`. */
export function formatTime(iso: string, tz: string): string {
  return inZone(iso, tz).toFormat("HH:mm");
}

/** `вт, 20 окт., 18:00–19:00`: день по началу занятия, конец считается по длительности. */
export function formatLessonWhen(iso: string, durationMin: number, tz: string): string {
  const start = inZone(iso, tz);
  const end = start.plus({ minutes: durationMin });
  return `${start.toFormat("ccc, d LLL")}, ${start.toFormat("HH:mm")}–${end.toFormat("HH:mm")}`;
}

/**
 * Местные дата (`2026-10-20`) и время (`18:00`) в поясе `tz` → момент в UTC (ISO, `…Z`).
 * Несуществующее местное время (пропуск при переходе на летнее) сдвигается вперёд, как на backend.
 */
export function zonedToUtcIso(date: string, time: string, tz: string): string {
  const moment = DateTime.fromISO(`${date}T${time}`, { zone: tz });
  if (!moment.isValid) throw new Error(`Некорректные дата и время: ${date} ${time} (${tz})`);
  const utc = moment.toUTC().toISO();
  if (utc === null) throw new Error(`Некорректные дата и время: ${date} ${time} (${tz})`);
  return utc;
}

/** Момент в UTC → местные дата (`yyyy-MM-dd`) и время (`HH:mm`) в поясе `tz`. */
export function utcToZonedParts(iso: string, tz: string): { date: string; time: string } {
  const moment = inZone(iso, tz);
  return { date: moment.toFormat("yyyy-MM-dd"), time: moment.toFormat("HH:mm") };
}

/** IANA-имя пояса браузера. */
export function browserTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

/**
 * Подпись пояса рядом со временем: `null`, если пояс браузера совпадает с `tz`,
 * иначе `время — {короткое имя}`; имя — то, что даёт `Intl` в ru-RU (`МСК`, `GMT+5`…).
 * `browserTz` можно подставить явно (в тестах).
 */
export function timeZoneNote(tz: string, browserTz: string = browserTimeZone()): string | null {
  if (tz === browserTz) return null;
  const name = new Intl.DateTimeFormat("ru-RU", { timeZone: tz, timeZoneName: "short" })
    .formatToParts(new Date())
    .find((part) => part.type === "timeZoneName")?.value;
  return name ? `время — ${name}` : null;
}
