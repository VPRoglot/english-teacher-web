import { expect, test } from "vitest";

import { formatPhoneInput } from "./phone-mask";

test.each([
  ["89991234567", "+7 (999) 123-45-67"],
  ["9991234567", "+7 (999) 123-45-67"],
  ["+7999", "+7 (999"],
  ["9991", "+7 (999) 1"],
  ["", ""],
  ["+44 20 7946", "+44 20 7946"],
])("formatPhoneInput(%s)", (raw, out) => expect(formatPhoneInput(raw)).toBe(out));

test.each([
  ["99912", "+7 (999) 12"],
  ["9991234", "+7 (999) 123-4"],
  ["999123456", "+7 (999) 123-45-6"],
  ["8", "+7"],
  ["+7 (999) 123-45-67", "+7 (999) 123-45-67"],
])("formatPhoneInput(%s) partial and idempotent", (raw, out) =>
  expect(formatPhoneInput(raw)).toBe(out));

test("never exceeds 18 characters for +7 numbers", () => {
  expect(formatPhoneInput("89991234567890123")).toBe("+7 (999) 123-45-67");
});

test("foreign numbers keep only digits, spaces and plus", () => {
  expect(formatPhoneInput("+44 (20) 7946-0000abc")).toBe("+44 20 79460000");
});
