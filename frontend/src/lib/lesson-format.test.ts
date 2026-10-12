import { expect, test } from "vitest";

import {
  LESSON_STATUS_LABELS,
  NEEDS_MARKING_LABEL,
  WEEKDAYS,
  buildRule,
  describeSeries,
  lessonEventClass,
  needsMarking,
  parseRule,
} from "./lesson-format";

const NOW = new Date("2026-10-20T12:00:00Z");

test("labels", () => {
  expect(LESSON_STATUS_LABELS).toEqual({
    scheduled: "Запланировано",
    completed: "Проведено",
    cancelled: "Отменено",
    cancelled_late: "Поздняя отмена",
    no_show: "Пропуск",
  });
  expect(NEEDS_MARKING_LABEL).toBe("Нужно отметить");
  expect(WEEKDAYS).toEqual([
    ["MO", "пн"],
    ["TU", "вт"],
    ["WE", "ср"],
    ["TH", "чт"],
    ["FR", "пт"],
    ["SA", "сб"],
    ["SU", "вс"],
  ]);
});

test("rule round trip matches backend canonical form", () => {
  expect(buildRule({ days: ["FR", "TU"], interval: 1 })).toBe("FREQ=WEEKLY;BYDAY=TU,FR");
  expect(buildRule({ days: ["MO"], interval: 2 })).toBe("FREQ=WEEKLY;INTERVAL=2;BYDAY=MO");
  expect(parseRule("FREQ=WEEKLY;INTERVAL=2;BYDAY=MO")).toEqual({ days: ["MO"], interval: 2 });
  expect(parseRule("FREQ=WEEKLY;BYDAY=TU,FR")).toEqual({ days: ["TU", "FR"], interval: 1 });
});

test("describes series", () => {
  expect(
    describeSeries({
      rrule: "FREQ=WEEKLY;BYDAY=TU,FR",
      local_start_time: "18:00:00",
      duration_min: 60,
    }),
  ).toBe("по вт и пт в 18:00, 60 мин");
  expect(
    describeSeries({
      rrule: "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO",
      local_start_time: "10:00",
      duration_min: 45,
    }),
  ).toBe("раз в 2 недели по пн в 10:00, 45 мин");
  expect(
    describeSeries({
      rrule: "FREQ=WEEKLY;BYDAY=MO,WE,FR",
      local_start_time: "09:30:00",
      duration_min: 30,
    }),
  ).toBe("по пн, ср и пт в 09:30, 30 мин");
});

test("needs marking", () => {
  expect(needsMarking({ status: "scheduled", starts_at: "2026-10-19T10:00:00Z" }, NOW)).toBe(true);
  expect(needsMarking({ status: "completed", starts_at: "2026-10-19T10:00:00Z" }, NOW)).toBe(false);
  expect(needsMarking({ status: "scheduled", starts_at: "2026-10-21T10:00:00Z" }, NOW)).toBe(false);
  expect(needsMarking({ status: "scheduled", starts_at: "2026-10-20T12:00:00Z" }, NOW)).toBe(true);
});

test("event classes distinguish status, trial and needs-marking", () => {
  const past = "2026-10-19T10:00:00Z";
  const future = "2026-10-21T10:00:00Z";
  const classes = [
    lessonEventClass({ status: "scheduled", kind: "regular", starts_at: future }, NOW),
    lessonEventClass({ status: "completed", kind: "regular", starts_at: past }, NOW),
    lessonEventClass({ status: "cancelled", kind: "regular", starts_at: future }, NOW),
    lessonEventClass({ status: "cancelled_late", kind: "regular", starts_at: past }, NOW),
    lessonEventClass({ status: "no_show", kind: "regular", starts_at: past }, NOW),
    lessonEventClass({ status: "scheduled", kind: "trial", starts_at: future }, NOW),
    lessonEventClass({ status: "scheduled", kind: "regular", starts_at: past }, NOW),
  ];
  expect(new Set(classes).size).toBe(6); // cancelled and cancelled_late share a class
  expect(classes[2]).toBe(classes[3]);
  expect(classes[6]).toContain("needs-marking");
  expect(classes[5]).toContain("trial");
});
