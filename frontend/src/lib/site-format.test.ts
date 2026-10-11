import { expect, test } from "vitest";

import { siteFixture } from "@/test/site-fixture";

import { contactLinks, formatRub, pluralRu } from "./site-format";

test.each([
  [0, "Бесплатно"],
  [1500, /^1\s500\s₽$/],
  [100000, /^100\s000\s₽$/],
])("formatRub(%s)", (value, expected) => {
  const result = formatRub(value);
  if (typeof expected === "string") {
    expect(result).toBe(expected);
  } else {
    expect(result).toMatch(expected);
  }
});

test.each([
  [1, "год"],
  [3, "года"],
  [5, "лет"],
  [11, "лет"],
  [18, "лет"],
  [21, "год"],
  [22, "года"],
])("pluralRu(%s)", (n, form) => {
  expect(pluralRu(n, ["год", "года", "лет"])).toBe(form);
});

test("contactLinks builds hrefs in fixed order", () => {
  expect(contactLinks(siteFixture.contacts).map((l) => l.href)).toEqual([
    "https://t.me/anna_english",
    "https://wa.me/79991234567",
    "tel:+79991234567",
    "mailto:anna@example.com",
  ]);
});

test("contactLinks labels telegram handle, WhatsApp, number and address", () => {
  expect(contactLinks(siteFixture.contacts).map((l) => l.label)).toEqual([
    "@anna_english",
    "WhatsApp",
    "+79991234567",
    "anna@example.com",
  ]);
});

test("contactLinks skips nulls", () => {
  const links = contactLinks({
    telegram: null,
    whatsapp: null,
    phone: null,
    email: "anna@example.com",
    working_hours_text: "Пн–Пт",
  });
  expect(links).toEqual([
    { kind: "email", label: "anna@example.com", href: "mailto:anna@example.com" },
  ]);
});
