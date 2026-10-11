import type { ContactMethod, LeadListItem, LeadStatus } from "@/api/generated/model";

export const LEAD_STATUS_LABELS: Record<LeadStatus, string> = {
  new: "Новая",
  contacted: "Связались",
  trial_scheduled: "Пробное назначено",
  converted: "Стала учеником",
  rejected: "Отказ",
};

export const LEAD_STATUS_BADGE_VARIANTS: Record<
  LeadStatus,
  "default" | "secondary" | "outline" | "destructive"
> = {
  new: "default",
  contacted: "secondary",
  trial_scheduled: "outline",
  converted: "secondary",
  rejected: "destructive",
};

export const CONTACT_METHOD_LABELS: Record<ContactMethod, string> = {
  telegram: "Telegram",
  whatsapp: "WhatsApp",
  phone: "Телефон",
};

const TELEGRAM_HANDLE_RE = /^[A-Za-z0-9_]{5,32}$/;

/** Ник без `@`, `t.me/` и `https://t.me/`; пустая строка, если ничего не осталось. */
function stripTelegramHandle(value: string): string {
  return value.trim().replace(/^(?:https?:\/\/)?t\.me\//i, "").replace(/^@/, "").trim();
}

/** Ссылка для связи: профиль в Telegram, чат WhatsApp или звонок. */
export function leadContactHref(
  lead: Pick<LeadListItem, "contact_method" | "messenger_handle" | "phone">,
): string {
  if (lead.contact_method === "telegram") {
    const handle = stripTelegramHandle(lead.messenger_handle ?? "");
    // Ссылку строим только из настоящего ника: произвольный ввод не должен попасть в URL.
    if (TELEGRAM_HANDLE_RE.test(handle)) return `https://t.me/${handle}`;
  }
  if (lead.contact_method === "whatsapp") {
    return `https://wa.me/${lead.phone.replace(/\D/g, "")}`;
  }
  return `tel:${lead.phone}`;
}
