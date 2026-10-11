const MOSCOW_FORMAT = new Intl.DateTimeFormat("ru-RU", {
  timeZone: "Europe/Moscow",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

/** `dd.MM.yyyy HH:mm` по московскому времени (ru-RU разделяет дату и время запятой). */
export function formatMoscow(iso: string): string {
  return MOSCOW_FORMAT.format(new Date(iso)).replace(",", "");
}
