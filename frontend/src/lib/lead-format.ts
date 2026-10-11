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

/** Ссылка для связи: профиль в Telegram, чат WhatsApp или звонок. */
export function leadContactHref(
  lead: Pick<LeadListItem, "contact_method" | "messenger_handle" | "phone">,
): string {
  if (lead.contact_method === "telegram") {
    const handle = lead.messenger_handle?.trim().replace(/^@/, "");
    if (handle) return `https://t.me/${handle}`;
  }
  if (lead.contact_method === "whatsapp") {
    return `https://wa.me/${lead.phone.replace(/\D/g, "")}`;
  }
  return `tel:${lead.phone}`;
}
