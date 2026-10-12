import { QueryClient } from "@tanstack/react-query";
import { expect, test, vi } from "vitest";

const warning = vi.fn();
vi.mock("sonner", () => ({ toast: { warning: (message: string) => warning(message) } }));

import {
  invalidateSchedule,
  isScheduleQueryKey,
  lessonsCount,
  seriesEditedMessage,
  toastWarnings,
} from "./lesson-mutations";

const STALE_KEYS = [
  ["/api/admin/lessons", { from: "2026-10-01T00:00:00Z", to: "2026-10-08T00:00:00Z" }],
  ["/api/admin/lessons/abc"],
  ["/api/admin/lessons/abc/notes"],
  ["/api/admin/series", { child_id: "c1" }],
  ["/api/admin/leads/lead-1/trial-lessons"],
  ["/api/admin/change-requests", { status: "pending" }],
  ["/api/admin/change-requests"],
  ["/api/admin/dashboard"],
];
const FRESH_KEYS = [
  ["/api/admin/leads"],
  ["/api/admin/leads/lead-1"],
  ["/api/admin/families", { q: "x" }],
  ["/api/admin/settings"],
  ["/api/me/lessons", { from: "x" }],
];

test("schedule predicate matches lessons, series and trial lessons of leads only", () => {
  expect(STALE_KEYS.map((key) => isScheduleQueryKey(key))).toEqual(STALE_KEYS.map(() => true));
  expect(FRESH_KEYS.map((key) => isScheduleQueryKey(key))).toEqual(FRESH_KEYS.map(() => false));
  expect(isScheduleQueryKey([{ not: "a string" }])).toBe(false);
  expect(isScheduleQueryKey([])).toBe(false);
});

test("invalidateSchedule marks lists, details, series and lead trial lessons as stale", () => {
  const client = new QueryClient();
  for (const key of [...STALE_KEYS, ...FRESH_KEYS]) client.setQueryData(key, []);

  invalidateSchedule(client);

  for (const key of STALE_KEYS) expect(client.getQueryState(key)?.isInvalidated).toBe(true);
  for (const key of FRESH_KEYS) expect(client.getQueryState(key)?.isInvalidated).toBe(false);
});

test("series edit message lists only non-zero parts", () => {
  expect(seriesEditedMessage({ created: 2, updated: 6, removed: 1 })).toBe(
    "Расписание изменено: обновлено 6 занятий, добавлено 2, удалено 1",
  );
  expect(seriesEditedMessage({ created: 0, updated: 1, removed: 0 })).toBe(
    "Расписание изменено: обновлено 1 занятие",
  );
  expect(seriesEditedMessage({ created: 3, updated: 0, removed: 0 })).toBe(
    "Расписание изменено: добавлено 3 занятия",
  );
  expect(seriesEditedMessage({ created: 0, updated: 0, removed: 5 })).toBe(
    "Расписание изменено: удалено 5 занятий",
  );
  expect(seriesEditedMessage({ created: 0, updated: 0, removed: 0 })).toBe("Расписание изменено");
});

test("each warning is a separate toast", () => {
  toastWarnings([
    { code: "overlap", lesson_id: "a", starts_at: "2026-10-20T15:00:00Z", message: "A" },
    { code: "overlap", lesson_id: "b", starts_at: "2026-10-21T15:00:00Z", message: "B" },
  ]);
  expect(warning.mock.calls).toEqual([["A"], ["B"]]);
});

test("pluralizes lessons in Russian", () => {
  expect(
    [0, 1, 2, 4, 5, 11, 12, 14, 21, 22, 25, 101, 111].map((count) => lessonsCount(count)),
  ).toEqual([
    "0 занятий",
    "1 занятие",
    "2 занятия",
    "4 занятия",
    "5 занятий",
    "11 занятий",
    "12 занятий",
    "14 занятий",
    "21 занятие",
    "22 занятия",
    "25 занятий",
    "101 занятие",
    "111 занятий",
  ]);
});
