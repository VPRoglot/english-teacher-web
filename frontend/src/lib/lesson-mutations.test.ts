import { QueryClient } from "@tanstack/react-query";
import { expect, test, vi } from "vitest";

const warning = vi.fn();
vi.mock("sonner", () => ({ toast: { warning: (message: string) => warning(message) } }));

import { invalidateSchedule, lessonsCount, toastWarnings } from "./lesson-mutations";

test("invalidates lesson and series queries by prefix", () => {
  const client = new QueryClient();
  const spy = vi.spyOn(client, "invalidateQueries");
  invalidateSchedule(client);
  expect(spy).toHaveBeenCalledWith({ queryKey: ["/api/admin/lessons"] });
  expect(spy).toHaveBeenCalledWith({ queryKey: ["/api/admin/series"] });
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
