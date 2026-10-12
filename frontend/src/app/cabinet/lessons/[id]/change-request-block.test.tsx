import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { ChangeRequestForFamily, LessonForFamilyDetail } from "@/api/generated/model";

import { ChangeRequestBlock } from "./change-request-block";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function makeRequest(overrides: Partial<ChangeRequestForFamily> = {}): ChangeRequestForFamily {
  return {
    id: "r1",
    type: "reschedule",
    status: "pending",
    proposed_text: "в четверг после 17",
    comment: "Болеем",
    tutor_response: null,
    created_at: "2026-10-12T08:00:00Z",
    resolved_at: null,
    is_late: false,
    ...overrides,
  };
}

function makeLesson(overrides: Partial<LessonForFamilyDetail> = {}): LessonForFamilyDetail {
  return {
    id: "l1",
    child_id: "c1",
    child_name: "Петя",
    duration_min: 60,
    has_shared_note: false,
    join_url: null,
    shared_note: null,
    starts_at: "2026-10-20T15:00:00Z",
    status: "scheduled",
    change_request: null,
    ...overrides,
  };
}

let role = "parent";
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-12T09:00:00Z"));
  role = "parent";
  document.cookie = "csrf_token=t";
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/auth/me") {
      return jsonResponse(200, {
        id: "u1",
        role,
        display_name: "Мария",
        email: null,
        username: null,
        family: null,
        children: [],
      });
    }
    if (url === "/api/me/schedule-settings") {
      return jsonResponse(200, { timezone: "Europe/Moscow", cancel_policy_hours: 24 });
    }
    if (url === "/api/me/change-requests/r1" && init?.method === "DELETE") {
      return jsonResponse(200, makeRequest({ status: "withdrawn" }));
    }
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

function renderBlock(lesson: LessonForFamilyDetail) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ChangeRequestBlock lesson={lesson} />
    </QueryClientProvider>,
  );
}

async function meLoaded() {
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/auth/me", expect.anything()));
  await new Promise((r) => setTimeout(r, 30));
}

test("parent sees request buttons for future scheduled lesson", async () => {
  renderBlock(makeLesson());
  expect(await screen.findByRole("button", { name: "Запросить перенос" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Запросить отмену" })).toBeInTheDocument();
});

test.each([
  ["past lesson", { starts_at: "2026-10-05T15:00:00Z" }],
  ["cancelled lesson", { status: "cancelled" }],
] as const)("no request buttons for %s", async (_name, overrides) => {
  renderBlock(makeLesson(overrides));
  await meLoaded();
  expect(screen.queryByRole("button", { name: "Запросить перенос" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Запросить отмену" })).not.toBeInTheDocument();
});

test("child sees no buttons", async () => {
  role = "child";
  renderBlock(makeLesson({ change_request: makeRequest() }));
  expect(await screen.findByText("Ждёт ответа репетитора")).toBeInTheDocument();
  await meLoaded();
  expect(screen.queryByRole("button", { name: /Запросить|Отозвать/ })).not.toBeInTheDocument();
});

test("pending request shows status and withdraw", async () => {
  const user = userEvent.setup();
  renderBlock(makeLesson({ change_request: makeRequest() }));
  expect(await screen.findByText("Ждёт ответа репетитора")).toBeInTheDocument();
  expect(screen.getByText("Перенос")).toBeInTheDocument();
  expect(screen.getByText(/в четверг после 17/)).toBeInTheDocument();
  expect(screen.getByText(/Болеем/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Запросить перенос" })).not.toBeInTheDocument();

  await user.click(await screen.findByRole("button", { name: "Отозвать запрос" }));
  const dialog = await screen.findByRole("dialog");
  expect(fetchMock).not.toHaveBeenCalledWith("/api/me/change-requests/r1", expect.anything());
  await user.click(within(dialog).getByRole("button", { name: "Отозвать" }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/me/change-requests/r1",
      expect.objectContaining({ method: "DELETE" }),
    ),
  );
});

test("rejected request shows tutor response and allows a new request", async () => {
  renderBlock(
    makeLesson({
      change_request: makeRequest({
        status: "rejected",
        tutor_response: "В четверг занят",
        resolved_at: "2026-10-12T08:30:00Z",
      }),
    }),
  );
  expect(await screen.findByText("Отклонён")).toBeInTheDocument();
  expect(screen.getByText("Ответ репетитора: В четверг занят")).toBeInTheDocument();
  expect(await screen.findByRole("button", { name: "Запросить перенос" })).toBeInTheDocument();
});

test("late cancel is marked", async () => {
  renderBlock(
    makeLesson({
      change_request: makeRequest({ type: "cancel", is_late: true, proposed_text: null }),
    }),
  );
  expect(await screen.findByText("Поздняя отмена")).toBeInTheDocument();
});
