import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { LessonForFamily } from "@/api/generated/model";

const push = vi.fn();
let search = "";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => "/cabinet/calendar",
  useSearchParams: () => new URLSearchParams(search),
}));

// FullCalendar itself is not exercised here: the mock lists the events and exposes its props,
// so the tests can fire datesSet / eventClick directly.
type CalendarProps = {
  events: { id: string; title: string }[];
  timeZone: string;
  initialView: string;
  noEventsContent?: string;
  datesSet: (arg: { start: Date; end: Date }) => void;
  eventClick: (arg: { event: { id: string }; jsEvent: { preventDefault: () => void } }) => void;
};
const calendar = vi.hoisted(() => ({ props: null as unknown }));
vi.mock("@fullcalendar/react", async () => {
  const React = await import("react");
  const Mock = React.forwardRef<unknown, CalendarProps>((props, ref) => {
    calendar.props = props;
    React.useImperativeHandle(ref, () => ({
      getApi: () => ({ view: { type: props.initialView }, changeView: () => {} }),
    }));
    return (
      <ul>
        {props.events.map((event) => (
          <li key={event.id}>{event.title}</li>
        ))}
      </ul>
    );
  });
  Mock.displayName = "MockFullCalendar";
  return { default: Mock };
});

import { CabinetCalendar, toCabinetEvents } from "./cabinet-calendar";

function props(): CalendarProps {
  return calendar.props as CalendarProps;
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function lesson(overrides: Partial<LessonForFamily> = {}): LessonForFamily {
  return {
    id: "1",
    child_id: "c1",
    child_name: "Петя",
    duration_min: 60,
    has_shared_note: false,
    join_url: null,
    starts_at: "2020-10-20T15:00:00Z",
    status: "scheduled",
    ...overrides,
  };
}

const KIDS = [
  { id: "c1", full_name: "Петя" },
  { id: "c2", full_name: "Маша" },
];

let children = KIDS;
let role: "parent" | "child" = "parent";
let lessons: LessonForFamily[] = [];
let fetchMock: ReturnType<typeof vi.fn>;

function stubApi() {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/auth/me") {
      return jsonResponse(200, {
        id: "u1",
        role,
        display_name: "Мария",
        email: null,
        username: null,
        family: null,
        children,
      });
    }
    if (url === "/api/me/schedule-settings") {
      return jsonResponse(200, { timezone: "Europe/Moscow", cancel_policy_hours: 24 });
    }
    if (url.startsWith("/api/me/lessons") && init?.method === "GET") {
      return jsonResponse(200, lessons);
    }
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function lessonRequests(): URL[] {
  return fetchMock.mock.calls
    .map(([url]) => String(url))
    .filter((url) => url.startsWith("/api/me/lessons?"))
    .map((url) => new URL(url, "http://localhost"));
}

function renderCalendar() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CabinetCalendar />
    </QueryClientProvider>,
  );
}

async function showRange() {
  await waitFor(() => expect(calendar.props).not.toBeNull());
  act(() =>
    props().datesSet({
      start: new Date("2026-10-01T00:00:00Z"),
      end: new Date("2026-11-01T00:00:00Z"),
    }),
  );
}

beforeEach(() => {
  push.mockReset();
  search = "";
  children = KIDS;
  role = "parent";
  lessons = [lesson()];
  calendar.props = null;
  document.cookie = "csrf_token=t";
  stubApi();
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test("toCabinetEvents titles by child name or a generic title", () => {
  const items = [lesson({ id: "1" }), lesson({ id: "2", child_id: "c2", child_name: "Маша" })];

  expect(toCabinetEvents(items, { showChildName: true }).map((e) => e.title)).toEqual([
    "Петя",
    "Маша",
  ]);
  expect(toCabinetEvents(items, { showChildName: false }).map((e) => e.title)).toEqual([
    "Английский",
    "Английский",
  ]);
  expect(toCabinetEvents([lesson()], { showChildName: false })[0]).toEqual({
    id: "1",
    title: "Английский",
    start: "2020-10-20T15:00:00Z",
    end: "2020-10-20T16:00:00.000Z",
    classNames: ["lesson-scheduled"],
  });
});

test("a past unmarked lesson is not painted as needing marking for the family", () => {
  const [past] = toCabinetEvents([lesson()], { showChildName: false });
  expect(past?.classNames).toEqual(["lesson-scheduled"]);
  const [done] = toCabinetEvents([lesson({ status: "completed" })], { showChildName: false });
  expect(done?.classNames).toEqual(["lesson-completed"]);
  const [late] = toCabinetEvents([lesson({ status: "cancelled_late" })], { showChildName: false });
  expect(late?.classNames).toEqual(["lesson-cancelled"]);
});

test("does not request lessons before the visible range is known", async () => {
  renderCalendar();
  await waitFor(() => expect(calendar.props).not.toBeNull());
  expect(lessonRequests()).toHaveLength(0);
});

test("opens on the month view and shows the empty text for list views", async () => {
  renderCalendar();
  await waitFor(() => expect(calendar.props).not.toBeNull());
  expect(props().initialView).toBe("dayGridMonth");
  expect(props().noEventsContent).toBe("Занятий нет");
});

test("fetches range for all children by default", async () => {
  renderCalendar();
  await showRange();
  await waitFor(() => expect(lessonRequests()).toHaveLength(1));
  const request = lessonRequests()[0];
  expect(request?.searchParams.get("from")).toBe("2026-10-01T00:00:00.000Z");
  expect(request?.searchParams.get("to")).toBe("2026-11-01T00:00:00.000Z");
  expect(request?.searchParams.has("child_id")).toBe(false);
});

test("fetches range with selected child", async () => {
  search = "child=c2";
  renderCalendar();
  await showRange();
  await waitFor(() => expect(lessonRequests()).toHaveLength(1));
  expect(lessonRequests()[0]?.searchParams.get("child_id")).toBe("c2");
});

test("unknown child in the url is ignored in the request", async () => {
  search = "child=zzz";
  renderCalendar();
  await showRange();
  await waitFor(() => expect(lessonRequests()).toHaveLength(1));
  expect(lessonRequests()[0]?.searchParams.has("child_id")).toBe(false);
});

test("event titles show child names only when several children", async () => {
  lessons = [lesson(), lesson({ id: "2", child_id: "c2", child_name: "Маша" })];
  const view = renderCalendar();
  await showRange();
  expect(await screen.findByText("Петя")).toBeInTheDocument();
  expect(screen.getByText("Маша")).toBeInTheDocument();
  view.unmount();

  calendar.props = null;
  children = [KIDS[0]!];
  lessons = [lesson()];
  renderCalendar();
  await showRange();
  expect(await screen.findByText("Английский")).toBeInTheDocument();
});

test("a child sees the generic title", async () => {
  role = "child";
  children = [KIDS[0]!];
  renderCalendar();
  await showRange();
  expect(await screen.findByText("Английский")).toBeInTheDocument();
});

test("event click opens the lesson page", async () => {
  renderCalendar();
  await showRange();
  await screen.findByText("Петя");
  act(() => props().eventClick({ event: { id: "1" }, jsEvent: { preventDefault: vi.fn() } }));
  expect(push).toHaveBeenCalledWith("/cabinet/lessons/1");
});

test("event click keeps child param", async () => {
  search = "child=c2";
  renderCalendar();
  await showRange();
  await waitFor(() => expect(lessonRequests()).toHaveLength(1));
  act(() => props().eventClick({ event: { id: "1" }, jsEvent: { preventDefault: vi.fn() } }));
  expect(push).toHaveBeenCalledWith("/cabinet/lessons/1?child=c2");
});

test("shows an error when the lessons cannot be loaded", async () => {
  const base = fetchMock.getMockImplementation() as (
    url: string,
    init?: RequestInit,
  ) => Promise<Response>;
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    if (url.startsWith("/api/me/lessons")) {
      return jsonResponse(500, { error: { code: "internal", message: "Сбой сервера", details: {} } });
    }
    return base(url, init);
  });
  renderCalendar();
  await showRange();
  expect(await screen.findByText("Сбой сервера")).toBeInTheDocument();
});
