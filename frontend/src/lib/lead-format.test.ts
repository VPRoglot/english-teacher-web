import { expect, test } from "vitest";

import { CONTACT_METHOD_LABELS, LEAD_STATUS_LABELS, leadContactHref } from "./lead-format";

test("contact href per method", () => {
  expect(
    leadContactHref({ contact_method: "telegram", messenger_handle: "@anna_en", phone: "+79991234567" }),
  ).toBe("https://t.me/anna_en");
  expect(
    leadContactHref({ contact_method: "telegram", messenger_handle: "anna_en", phone: "+79991234567" }),
  ).toBe("https://t.me/anna_en");
  expect(
    leadContactHref({ contact_method: "whatsapp", messenger_handle: null, phone: "+79991234567" }),
  ).toBe("https://wa.me/79991234567");
  expect(
    leadContactHref({ contact_method: "phone", messenger_handle: null, phone: "+79991234567" }),
  ).toBe("tel:+79991234567");
});

test.each([
  ["@olga_test", "https://t.me/olga_test"],
  ["https://t.me/olga_test", "https://t.me/olga_test"],
  ["t.me/olga_test", "https://t.me/olga_test"],
  ["T.ME/olga_test", "https://t.me/olga_test"],
])("telegram handle %s links to the profile", (handle, href) => {
  expect(
    leadContactHref({ contact_method: "telegram", messenger_handle: handle, phone: "+79991234567" }),
  ).toBe(href);
});

test.each(["olga test", "ol", "olga/test?x=1", "@@olga_test", "javascript:alert(1)"])(
  "telegram handle %j is not a valid username and falls back to the phone",
  (handle) => {
    expect(
      leadContactHref({ contact_method: "telegram", messenger_handle: handle, phone: "+79991234567" }),
    ).toBe("tel:+79991234567");
  },
);

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
