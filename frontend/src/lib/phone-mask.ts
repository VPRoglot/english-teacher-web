const NATIONAL_LENGTH = 10;
const FOREIGN_MAX_LENGTH = 20;

/** Российский номер по цифрам без кода страны: «+7 (999) 123-45-67», в том числе неполный. */
function formatRussian(national: string): string {
  if (national === "") return "+7";
  const a = national.slice(0, 3);
  const b = national.slice(3, 6);
  const c = national.slice(6, 8);
  const d = national.slice(8, 10);
  let result = `+7 (${a}`;
  if (b) result += `) ${b}`;
  if (c) result += `-${c}`;
  if (d) result += `-${d}`;
  return result;
}

/**
 * Маска телефона при вводе. Номер без «+» и с «+7» считается российским и приводится к
 * «+7 (999) 123-45-67»; ведущие 7 и 8 — код страны. Номер с другим кодом страны остаётся
 * как есть, из него убирается всё, кроме цифр, пробелов и «+».
 */
export function formatPhoneInput(raw: string): string {
  const text = raw.trimStart();
  if (text === "") return "";

  if (text.startsWith("+") && !text.startsWith("+7")) {
    return text.replace(/[^\d\s+]/g, "").slice(0, FOREIGN_MAX_LENGTH);
  }

  let digits = text.replace(/\D/g, "");
  if (digits.startsWith("7") || digits.startsWith("8")) digits = digits.slice(1);
  return formatRussian(digits.slice(0, NATIONAL_LENGTH));
}
