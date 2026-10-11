import { expect, test } from "vitest";

import { CONTACT_METHOD_LABELS, LEAD_STATUS_LABELS, leadContactHref } from "./lead-format";

test("contact href per method", () => {
  expect(
    leadContactHref({ contact_method: "telegram", messenger_handle: "@anna", phone: "+79991234567" }),
  ).toBe("https://t.me/anna");
  expect(
    leadContactHref({ contact_method: "telegram", messenger_handle: "anna", phone: "+79991234567" }),
  ).toBe("https://t.me/anna");
  expect(
    leadContactHref({ contact_method: "whatsapp", messenger_handle: null, phone: "+79991234567" }),
  ).toBe("https://wa.me/79991234567");
  expect(
    leadContactHref({ contact_method: "phone", messenger_handle: null, phone: "+79991234567" }),
  ).toBe("tel:+79991234567");
});

test("telegram without a handle falls back to the phone", () => {
  expect(
    leadContactHref({ contact_method: "telegram", messenger_handle: null, phone: "+79991234567" }),
  ).toBe("tel:+79991234567");
  expect(
    leadContactHref({ contact_method: "telegram", messenger_handle: "  ", phone: "+79991234567" }),
  ).toBe("tel:+79991234567");
});

test("labels are in Russian", () => {
  expect(LEAD_STATUS_LABELS).toEqual({
    new: "Новая",
    contacted: "Связались",
    trial_scheduled: "Пробное назначено",
    converted: "Стала учеником",
    rejected: "Отказ",
  });
  expect(CONTACT_METHOD_LABELS).toEqual({
    telegram: "Telegram",
    whatsapp: "WhatsApp",
    phone: "Телефон",
  });
});
