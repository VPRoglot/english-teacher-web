import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { LessonCalendar } from "./lesson-calendar";

const VIEWS = { desktop: ["timeGridWeek", "timeGridDay"], mobile: "listWeek" };

// The calendar opens on the current week, so the event starts "now" — a frozen now. With the real
// clock an hour-long event started after 23:00 crosses midnight, the time grid splits it into two
// segments and "Петя" appears twice. 09:00Z is daytime in every zone these tests render
// (UTC 09:00, Moscow 12:00, Tokyo 18:00).
const NOW = Date.parse("2026-10-14T09:00:00Z");
const EVENT = {
  id: "l1",
  title: "Петя",
  start: new Date(NOW).toISOString(),
  end: new Date(NOW + 3_600_000).toISOString(),
};

function stubMatchMedia(matches: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: NOW });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function renderCalendar(overrides: Partial<React.ComponentProps<typeof LessonCalendar>> = {}) {
  const onRangeChange = vi.fn();
  const onEventClick = vi.fn();
  const utils = render(
    <LessonCalendar
      timeZone="Europe/Moscow"
      views={VIEWS}
      events={[EVENT]}
      onRangeChange={onRangeChange}
      onEventClick={onEventClick}
      {...overrides}
    />,
  );
  return { ...utils, onRangeChange, onEventClick };
}

test("desktop shows the first desktop view in Russian and reports the visible range", async () => {
  stubMatchMedia(false);
  const { container, onRangeChange } = renderCalendar();

  expect(await screen.findByText("Петя")).toBeInTheDocument();
  expect(container.querySelector(".fc-timeGridWeek-view")).not.toBeNull();
  expect(screen.getByRole("button", { name: /Сегодня|сегодня/ })).toBeInTheDocument();
  await waitFor(() => expect(onRangeChange).toHaveBeenCalled());
  const [start, end] = onRangeChange.mock.calls[0] as [Date, Date];
  expect(end.getTime()).toBeGreaterThan(start.getTime());
});

test("mobile shows the list view without the view switcher", async () => {
  stubMatchMedia(true);
  const { container } = renderCalendar();

  await waitFor(() => expect(container.querySelector(".fc-list")).not.toBeNull());
  expect(container.querySelector(".fc-timeGridWeek-button")).toBeNull();
});

test("clicking an event reports its id", async () => {
  stubMatchMedia(false);
  const { onEventClick } = renderCalendar();

  await userEvent.click(await screen.findByText("Петя"));
  expect(onEventClick).toHaveBeenCalledWith("l1");
});

test("an empty list range shows the given text", async () => {
  stubMatchMedia(true);
  renderCalendar({ events: [], emptyText: "Занятий нет" });
  expect(await screen.findByText("Занятий нет")).toBeInTheDocument();
});

test("renders without matchMedia", async () => {
  vi.stubGlobal("matchMedia", undefined);
  renderCalendar();
  expect(await screen.findByText("Петя")).toBeInTheDocument();
});

test("shows the zone note only when the browser zone differs", async () => {
  stubMatchMedia(false);
  const browser = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const other = browser === "Asia/Tokyo" ? "Europe/Moscow" : "Asia/Tokyo";
  const { unmount } = renderCalendar({ timeZone: other });
  expect(await screen.findByText(/^время — /)).toBeInTheDocument();
  unmount();
  renderCalendar({ timeZone: browser });
  await screen.findByText("Петя");
  expect(screen.queryByText(/^время — /)).not.toBeInTheDocument();
});
