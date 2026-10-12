import { expect, test } from "vitest";

import {
  DEFAULT_TIME_ZONE,
  browserTimeZone,
  formatDate,
  formatDateTime,
  formatLessonWhen,
  formatTime,
  timeZoneNote,
  utcToZonedParts,
  zonedToUtcIso,
} from "./datetime";

test("default zone is Moscow", () => {
  expect(DEFAULT_TIME_ZONE).toBe("Europe/Moscow");
});

test("zoned wall time to UTC", () => {
  expect(zonedToUtcIso("2026-10-20", "18:00", "Europe/Moscow")).toBe("2026-10-20T15:00:00.000Z");
  expect(zonedToUtcIso("2026-03-31", "10:00", "Europe/Berlin")).toBe("2026-03-31T08:00:00.000Z");
});

test("zoned wall time converts per date across a DST change", () => {
  expect(zonedToUtcIso("2026-03-24", "10:00", "Europe/Berlin")).toBe("2026-03-24T09:00:00.000Z");
});

test("a wall time that does not exist moves forward instead of failing", () => {
  expect(zonedToUtcIso("2026-03-29", "02:30", "Europe/Berlin")).toBe("2026-03-29T01:30:00.000Z");
});

test("invalid wall time throws", () => {
  expect(() => zonedToUtcIso("2026-13-40", "18:00", "Europe/Moscow")).toThrow();
});

test("UTC to zoned parts", () => {
  expect(utcToZonedParts("2026-10-20T15:00:00Z", "Asia/Yekaterinburg")).toEqual({
    date: "2026-10-20",
    time: "20:00",
  });
});

test("UTC to zoned parts crosses midnight", () => {
  expect(utcToZonedParts("2026-10-20T22:30:00Z", "Europe/Moscow")).toEqual({
    date: "2026-10-21",
    time: "01:30",
  });
});

test("formats in the tutor zone, not the browser zone", () => {
  expect(formatDateTime("2026-10-20T15:00:00Z", "Europe/Moscow")).toBe("20.10.2026 18:00");
  expect(formatDateTime("2026-10-20T15:00:00Z", "Asia/Yekaterinburg")).toBe("20.10.2026 20:00");
  expect(formatDate("2026-10-20T22:30:00Z", "Europe/Moscow")).toBe("21.10.2026");
  expect(formatTime("2026-10-20T15:00:00Z", "Europe/Moscow")).toBe("18:00");
  expect(formatLessonWhen("2026-10-20T15:00:00Z", 60, "Europe/Moscow")).toBe(
    "вт, 20 окт., 18:00–19:00",
  );
});

test("lesson end time may fall on the next day", () => {
  expect(formatLessonWhen("2026-10-20T20:30:00Z", 60, "Europe/Moscow")).toBe(
    "вт, 20 окт., 23:30–00:30",
  );
});

test("browser zone is a non-empty IANA name", () => {
  expect(browserTimeZone().length).toBeGreaterThan(0);
});

test("zone note only when the browser zone differs", () => {
  expect(timeZoneNote("Europe/Moscow", "Europe/Moscow")).toBeNull();
  // Ruling 2: the short name is whatever Intl yields in ru-RU in this environment.
  const short = new Intl.DateTimeFormat("ru-RU", {
    timeZone: "Europe/Moscow",
    timeZoneName: "short",
  })
    .formatToParts(new Date())
    .find((part) => part.type === "timeZoneName")?.value;
  expect(short).toBeTruthy();
  expect(timeZoneNote("Europe/Moscow", "Asia/Tokyo")).toBe(`время — ${short}`);
});
