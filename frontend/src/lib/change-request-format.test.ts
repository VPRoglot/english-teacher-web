import { expect, test } from "vitest";

import {
  CHANGE_REQUEST_STATUS_LABELS,
  CHANGE_REQUEST_TYPE_LABELS,
  isLateNow,
} from "./change-request-format";

const STARTS = "2026-10-13T12:00:00Z";

test("late when less than policy hours left", () => {
  expect(isLateNow(STARTS, 24, new Date("2026-10-12T12:01:00Z"))).toBe(true); // 23:59 до начала
  expect(isLateNow(STARTS, 24, new Date("2026-10-12T11:59:00Z"))).toBe(false); // 24:01
});

test("exactly policy hours before start is not late", () => {
  expect(isLateNow(STARTS, 24, new Date("2026-10-12T12:00:00Z"))).toBe(false);
});

test("zero policy is never late", () => {
  expect(isLateNow(STARTS, 0, new Date("2026-10-13T11:59:00Z"))).toBe(false);
});

test("labels", () => {
  expect(CHANGE_REQUEST_TYPE_LABELS.cancel).toBe("Отмена");
  expect(CHANGE_REQUEST_STATUS_LABELS.pending).toBe("Ждёт ответа репетитора");
});
