import path from "node:path";

/** Адрес стека: nginx с self-signed сертификатом, сетевой alias в compose. */
export const BASE_URL = process.env.E2E_BASE_URL ?? "https://tutor.test";

/** Сессия репетитора, которую сохраняет global-setup. */
export const TUTOR_STATE = path.join(__dirname, ".auth", "tutor.json");

/** Репетитора создаёт раннер (`e2e/create-tutor.sh` в api) с этими данными из infra/e2e.env. */
export const TUTOR = {
  email: process.env.E2E_TUTOR_EMAIL ?? "tutor@example.com",
  get password(): string {
    const value = process.env.E2E_TUTOR_PASSWORD;
    if (!value) throw new Error("E2E_TUTOR_PASSWORD не задан (infra/e2e.env)");
    return value;
  },
};

/**
 * Тестовые учётные данные семьи (только для стека tutor.test); создаются сценариями 2 и 7.
 * Email — на example.com (RFC 2606): адреса на `.test` backend отклоняет (email-validator
 * запрещает special-use домены), а example.com никогда не доставляется.
 */
export const PARENT = { email: "parent1@example.com", password: "e2e-parent-pass-2026" };
export const CHILD = { username: "petya-e2e", password: "e2e-child-pass" };

/** Данные заявки (сценарий 1): по ним следующие сценарии находят заявку, семью и детей. */
export const LEAD = {
  parentName: "Анна Иванова",
  childName: "Петя",
  childAge: "9",
  phone: "+79991234567",
  telegram: "@anna_e2e",
};

/** Второй ребёнок семьи (сценарий 3): его занятий не должно быть у первого (сценарий 7). */
export const SIBLING = { name: "Маша" };
