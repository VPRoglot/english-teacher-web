import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { AdminLessonItem } from "@/api/generated/model";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), warning: vi.fn() } }));

// FullCalendar itself is not exercised here: the mock lists the events and exposes its props,
// so the tests can fire datesSet / dateClick / eventClick directly.
type CalendarProps = {
  events: { id: string; title: string }[];
  timeZone: string;
  initialView: string;
  datesSet: (arg: { start: Date; end: Date }) => void;
  dateClick: (arg: { date: Date }) => void;
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

import { AdminCalendar, toAdminEvents } from "./admin-calendar";

function props(): CalendarProps {
  return calendar.props as CalendarProps;
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function lesson(overrides: Partial<AdminLessonItem> = {}): AdminLessonItem {
  return {
    id: "1",
    duration_min: 60,
    has_notes: false,
    is_detached: false,
    join_url: null,
    kind: "regular",
    meeting_url: null,
    series_id: null,
    starts_at: "2026-10-20T15:00:00Z",
    status: "scheduled",
    student: { child_id: "c1", lead_id: null, name: "Петя", family_id: "f1", family_name: "Ивановы" },
    ...overrides,
  };
}

const NOW = new Date("2026-10-15T10:00:00Z");

test("maps lessons to events with trial prefix and marking class", () => {
  const events = toAdminEvents(
    [
      lesson({ id: "1", starts_at: "2026-10-20T15:00:00Z" }),
      lesson({
        id: "2",
        kind: "trial",
        starts_at: "2026-10-21T15:00:00Z",
        duration_min: 30,
        student: { child_id: null, lead_id: "x", name: "Петя", family_id: null, family_name: null },
      }),
      lesson({ id: "3", starts_at: "2026-10-14T15:00:00Z" }),
      lesson({ id: "4", starts_at: "2026-10-14T16:00:00Z", status: "completed" }),
    ],
    NOW,
  );

  expect(events).toEqual([
    {
      id: "1",
      title: "Петя",
      start: "2026-10-20T15:00:00Z",
      end: "2026-10-20T16:00:00.000Z",
      classNames: ["lesson-scheduled"],
    },
    {
      id: "2",
      title: "Пробное: Петя",
      start: "2026-10-21T15:00:00Z",
      end: "2026-10-21T15:30:00.000Z",
      classNames: ["lesson-trial"],
    },
    {
      id: "3",
      title: "Петя",
      start: "2026-10-14T15:00:00Z",
      end: "2026-10-14T16:00:00.000Z",
      classNames: ["lesson-needs-marking"],
    },
    {
      id: "4",
      title: "Петя",
      start: "2026-10-14T16:00:00Z",
      end: "2026-10-14T17:00:00.000Z",
      classNames: ["lesson-completed"],
    },
  ]);
});

let timezone = "Europe/Moscow";
let lessons: AdminLessonItem[] = [];
let fetchMock: ReturnType<typeof vi.fn>;

function stubApi() {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/admin/settings") {
      return jsonResponse(200, { timezone, cancel_policy_hours: 24 });
    }
    if (url.startsWith("/api/admin/lessons") && init?.method === "GET") {
      return jsonResponse(200, lessons);
    }
    if (url.startsWith("/api/admin/families") && init?.method === "GET") return jsonResponse(200, []);
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function lessonRequests(): URL[] {
  return fetchMock.mock.calls
    .map(([url]) => String(url))
    .filter((url) => url.startsWith("/api/admin/lessons?"))
    .map((url) => new URL(url, "http://localhost"));
}

function renderCalendar() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AdminCalendar />
    </QueryClientProvider>,
  );
}

async function showRange() {
  await waitFor(() => expect(calendar.props).not.toBeNull());
  act(() =>
    props().datesSet({
      start: new Date("2026-10-19T00:00:00Z"),
      end: new Date("2026-10-26T00:00:00Z"),
    }),
  );
}

beforeEach(() => {
  push.mockReset();
  timezone = "Europe/Moscow";
  lessons = [lesson()];
  calendar.props = null;
  document.cookie = "csrf_token=t";
  stubApi();
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test("does not request lessons before the visible range is known", async () => {
  renderCalendar();
  await waitFor(() => expect(calendar.props).not.toBeNull());
  expect(lessonRequests()).toHaveLength(0);
});

test("opens on the week view", async () => {
  renderCalendar();
  await waitFor(() => expect(calendar.props).not.toBeNull());
  expect(props().initialView).toBe("timeGridWeek");
});

test("range change fetches lessons for the visible range", async () => {
  renderCalendar();
  await showRange();

  await waitFor(() => expect(lessonRequests()).toHaveLength(1));
  const request = lessonRequests()[0];
  expect(request?.searchParams.get("from")).toBe("2026-10-19T00:00:00.000Z");
  expect(request?.searchParams.get("to")).toBe("2026-10-26T00:00:00.000Z");
  expect(await screen.findByText("Петя")).toBeInTheDocument();
});

test("keeps showing the previous range while the next one loads", async () => {
  renderCalendar();
  await showRange();
  expect(await screen.findByText("Петя")).toBeInTheDocument();

  fetchMock.mockImplementation(() => new Promise(() => {}));
  act(() =>
    props().datesSet({
      start: new Date("2026-10-26T00:00:00Z"),
      end: new Date("2026-11-02T00:00:00Z"),
    }),
  );
  expect(screen.getByText("Петя")).toBeInTheDocument();
});

test("event click opens the lesson page", async () => {
  renderCalendar();
  await showRange();
  await screen.findByText("Петя");

  const preventDefault = vi.fn();
  act(() => props().eventClick({ event: { id: "1" }, jsEvent: { preventDefault } }));
  expect(push).toHaveBeenCalledWith("/admin/lessons/1");
});

test("slot click opens dialog prefilled in tutor zone", async () => {
  timezone = "Asia/Yekaterinburg";
  renderCalendar();
  await waitFor(() => expect(props().timeZone).toBe("Asia/Yekaterinburg"));

  act(() => props().dateClick({ date: new Date("2026-10-20T15:00:00Z") }));

  expect(await screen.findByLabelText("Дата")).toHaveValue("2026-10-20");
  expect(screen.getByLabelText("Время")).toHaveValue("20:00");
});

test("the add button opens the dialog with the nearest full hour", async () => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-20T13:20:00Z"));
  try {
    renderCalendar();
    await waitFor(() => expect(calendar.props).not.toBeNull());
    await userEvent.click(screen.getByRole("button", { name: "Добавить занятие" }));

    expect(await screen.findByLabelText("Дата")).toHaveValue("2026-10-20");
    expect(screen.getByLabelText("Время")).toHaveValue("17:00");
  } finally {
    vi.useRealTimers();
  }
});

test("shows an error when the lessons cannot be loaded", async () => {
  fetchMock.mockImplementation(async (url: string) => {
    if (url === "/api/admin/settings") {
      return jsonResponse(200, { timezone, cancel_policy_hours: 24 });
    }
    return jsonResponse(500, { error: { code: "internal", message: "Сбой сервера", details: {} } });
  });
  renderCalendar();
  await showRange();

  expect(await screen.findByText("Сбой сервера")).toBeInTheDocument();
});
