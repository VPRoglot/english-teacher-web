import type { ContactsBlock } from "@/api/generated/model";

const rubFormatter = new Intl.NumberFormat("ru-RU");

/** `0` — «Бесплатно», иначе сумма с разделителем тысяч и знаком рубля. */
export function formatRub(value: number): string {
  return value === 0 ? "Бесплатно" : `${rubFormatter.format(value)} ₽`;
}

/** Склонение по числу: [1 год, 2 года, 5 лет]. */
export function pluralRu(n: number, forms: [string, string, string]): string {
  const lastTwo = Math.abs(n) % 100;
  const last = lastTwo % 10;
  if (lastTwo > 10 && lastTwo < 20) return forms[2];
  if (last === 1) return forms[0];
  if (last >= 2 && last <= 4) return forms[1];
  return forms[2];
}

export type ContactLink = {
  kind: "telegram" | "whatsapp" | "phone" | "email";
  label: string;
  href: string;
};

/** Ссылки на заполненные контакты в фиксированном порядке: telegram, whatsapp, phone, email. */
export function contactLinks(contacts: ContactsBlock): ContactLink[] {
  const links: ContactLink[] = [];
  if (contacts.telegram) {
    links.push({
      kind: "telegram",
      label: `@${contacts.telegram}`,
      href: `https://t.me/${contacts.telegram}`,
    });
  }
  const whatsappDigits = contacts.whatsapp?.replace(/\D/g, "");
  if (whatsappDigits) {
    links.push({ kind: "whatsapp", label: "WhatsApp", href: `https://wa.me/${whatsappDigits}` });
  }
  if (contacts.phone) {
    links.push({ kind: "phone", label: contacts.phone, href: `tel:${contacts.phone}` });
  }
  if (contacts.email) {
    links.push({ kind: "email", label: contacts.email, href: `mailto:${contacts.email}` });
  }
  return links;
}
