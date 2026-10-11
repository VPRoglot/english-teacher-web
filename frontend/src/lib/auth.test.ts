import { expect, test } from "vitest";

import { homeFor, safeNext } from "./auth";

test.each([
  ["/cabinet", "/cabinet"],
  ["/admin/families?x=1", "/admin/families?x=1"],
  ["//evil.com", null],
  ["https://evil.com", null],
  ["/\\evil.com", null],
  ["evil", null],
  [null, null],
  ["", null],
  ["/a\nb", null],
  ["/a\tb", null],
])("safeNext(%j) → %j", (input, expected) => {
  expect(safeNext(input)).toBe(expected);
});

test("homeFor", () => {
  expect(homeFor("tutor")).toBe("/admin");
  expect(homeFor("parent")).toBe("/cabinet");
  expect(homeFor("child")).toBe("/cabinet");
});
