import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { AdminLessonItem, DashboardResponse } from "@/api/generated/model";

import { Dashboard } from "./dashboard";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function lessonItem(id: string, name: string, startsAt: string): AdminLessonItem {
  return {
    id,
    starts_at: startsAt,
    duration_min: 60,
    status: "scheduled",
    kind: "regular",
    series_id: null,
    is_detached: false,
    has_notes: false,
    join_url: null,
    meeting_url: null,
    student: { child_id: "c1", lead_id: null, name, family_id: "f1", family_name: "Ивановы" },
  };
}

const FILLED: DashboardResponse = {
  timezone: "Asia/Yekaterinburg",
  new_leads: {
    total: 7,
    items: [
      {
        id: "n1",
        parent_name: "Ольга Смирнова",
        child_name: "Маша",
        child_age: 8,
        contact_method: "telegram",
        messenger_handle: "olga_s",
        phone: "+79000000000",
        status: "new",
        created_at: "2026-10-12T08:00:00Z",
      },
    ],
  },
  pending_requests: {
    total: 3,
    items: [
      {
        id: "r1",
        type: "cancel",
        status: "pending",
        proposed_text: null,
        comment: null,
        tutor_response: null,
        created_at: "2026-10-12T08:00:00Z",
        resolved_at: null,
        is_late: false,
        // 20.10 20:00 в Екатеринбурге
        lesson: { id: "l9", starts_at: "2026-10-20T15:00:00Z", duration_min: 60, status: "scheduled" },
        child: { id: "c1", full_name: "Петя Иванов" },
        family: { id: "f1", name: "Ивановы" },
        requested_by_name: "Анна",
      },
    ],
  },
  needs_marking: {
    total: 12,
    items: [lessonItem("m1", "Вася", "2026-10-11T10:00:00Z")], // 15:00
  },
  today: [lessonItem("t1", "Катя", "2026-10-13T05:00:00Z")], // 10:00
};

const EMPTY: DashboardResponse = {
  timezone: "Asia/Yekaterinburg",
  new_leads: { total: 0, items: [] },
  pending_requests: { total: 0, items: [] },
  needs_marking: { total: 0, items: [] },
  today: [],
};

function renderDashboard(data: DashboardResponse) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url === "/api/admin/dashboard") return jsonResponse(200, data);
      throw new Error(`unexpected fetch ${url}`);
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Dashboard />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-10-13T04:00:00Z") });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function card(name: RegExp): HTMLElement {
  return screen.getByRole("region", { name });
}

test("dashboard shows counts and links", async () => {
  renderDashboard(FILLED);

  expect(await screen.findByRole("heading", { name: "Новые заявки · 7" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Ждут ответа · 3" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Нужно отметить · 12" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Сегодня · 1" })).toBeInTheDocument();

  const leads = card(/Новые заявки/);
  expect(within(leads).getByRole("link", { name: /Ольга Смирнова/ })).toHaveAttribute(
    "href",
    "/admin/leads/n1",
  );
  expect(within(leads).getByText(/Маша, 8 лет/)).toBeInTheDocument();
  expect(within(leads).getByText(/12\.10\.2026 13:00/)).toBeInTheDocument();
  expect(within(leads).getByRole("link", { name: "Все заявки" })).toHaveAttribute(
    "href",
    "/admin/leads?status=new",
  );

  const requests = card(/Ждут ответа/);
  expect(within(requests).getByText("Отмена")).toBeInTheDocument();
  expect(within(requests).getByText(/Петя Иванов/)).toBeInTheDocument();
  expect(within(requests).getByText(/20:00–21:00/)).toBeInTheDocument();
  expect(within(requests).getByRole("link", { name: "Открыть очередь" })).toHaveAttribute(
    "href",
    "/admin/requests",
  );

  const marking = card(/Нужно отметить/);
  expect(within(marking).getByRole("link", { name: /Вася/ })).toHaveAttribute(
    "href",
    "/admin/lessons/m1",
  );
  expect(within(marking).getByText(/15:00–16:00/)).toBeInTheDocument();

  const today = card(/Сегодня/);
  expect(within(today).getByRole("link", { name: /Катя/ })).toHaveAttribute(
    "href",
    "/admin/lessons/t1",
  );
  expect(within(today).getByText(/10:00–11:00/)).toBeInTheDocument();
});

test("empty sections show placeholders", async () => {
  renderDashboard(EMPTY);

  expect(await screen.findByText("Новых заявок нет")).toBeInTheDocument();
  expect(screen.getByText("Запросов нет")).toBeInTheDocument();
  expect(screen.getByText("Все занятия отмечены")).toBeInTheDocument();
  expect(screen.getByText("Сегодня занятий нет")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Новые заявки · 0" })).toBeInTheDocument();
});
