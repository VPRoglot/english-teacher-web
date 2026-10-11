const STORAGE_KEY = "utm";
const MAX_LENGTH = 100;
const KEYS = ["utm_source", "utm_medium", "utm_campaign"] as const;

export type Utm = { utm_source?: string; utm_medium?: string; utm_campaign?: string };

/**
 * Запоминает UTM-метки из адресной строки на время сессии вкладки: заявка может уйти
 * уже после перехода по страницам. Адрес без меток прежние значения не стирает.
 */
export function captureUtm(search: string): void {
  const params = new URLSearchParams(search);
  const utm: Utm = {};
  for (const key of KEYS) {
    const value = params.get(key)?.trim().slice(0, MAX_LENGTH);
    if (value) utm[key] = value;
  }
  if (Object.keys(utm).length === 0) return;
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(utm));
  } catch {
    // sessionStorage недоступен (приватный режим, запрет cookie) — заявка уйдёт без меток.
  }
}

/** Сохранённые метки; недоступное или испорченное хранилище даёт пустой объект. */
export function readUtm(): Utm {
  try {
    const stored: unknown = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "{}");
    if (typeof stored !== "object" || stored === null) return {};
    const utm: Utm = {};
    for (const key of KEYS) {
      const value = (stored as Record<string, unknown>)[key];
      if (typeof value === "string" && value) utm[key] = value.slice(0, MAX_LENGTH);
    }
    return utm;
  } catch {
    return {};
  }
}
