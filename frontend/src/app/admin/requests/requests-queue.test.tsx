import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const toastSuccess = vi.fn();
const toastWarning = vi.fn();
vi.mock("sonner", () => ({
  toast: {
    success: (message: string) => toastSuccess(message),
    warning: (message: string) => toastWarning(message),
  },
}));

const replace = vi.fn();
let search = "";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/admin/requests",
  useSearchParams: () => new URLSearchParams(search),
}));

import type { ChangeRequestAdminItem } from "@/api/generated/model";

import { RequestsQueue } from "./requests-queue";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function item(overrides: Partial<ChangeRequestAdminItem> = {}): ChangeRequestAdminItem {
  return {
    id: "r1",
    type: "reschedule",
    status: "pending",
    proposed_text: "в четверг после 17:00",
    comment: "Болеем",
    tutor_response: null,
    created_at: "2026-10-12T08:00:00Z",
    resolved_at: null,
    is_late: false,
    // 20.10 20:00 в Екатеринбурге
    lesson: { id: "l1", starts_at: "2026-10-20T15:00:00Z", duration_min: 60, status: "scheduled" },
    child: { id: "c1", full_name: "Петя Иванов" },
    family: { id: "f1", name: "Ивановы" },
    requested_by_name: "Анна",
    ...overrides,
  };
}

let fetchMock: ReturnType<typeof vi.fn>;
let listResponse: (url: string) => Response;
let actionResponse: () => Response;
const timezone = "Asia/Yekaterinburg";

function stubApi() {
  fetchMock = vi.fn(async (url: string) => {
    if (url.startsWith("/api/admin/change-requests?") || url === "/api/admin/change-requests") {
      return listResponse(url);
    }
    if (url === "/api/admin/settings") {
      return jsonResponse(200, { timezone, cancel_policy_hours: 24 });
    }
    if (/\/api\/admin\/change-requests\/r\d\/(approve|reject)$/.test(url)) return actionResponse();
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function actionCalls(kind: "approve" | "reject"): { url: string; body: unknown }[] {
  return fetchMock.mock.calls
    .filter(([url, init]) => String(url).endsWith(`/${kind}`) && init?.method === "POST")
    .map(([url, init]) => ({
      url: String(url),
      body: JSON.parse((init as RequestInit).body as string),
    }));
}

let client: QueryClient;
function renderQueue() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.spyOn(client, "invalidateQueries");
  return render(
    <QueryClientProvider client={client}>
      <RequestsQueue />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-10-12T10:00:00Z") });
  search = "";
  replace.mockReset();
  toastSuccess.mockReset();
  toastWarning.mockReset();
  listResponse = () => jsonResponse(200, [item()]);
  actionResponse = () => jsonResponse(200, { ...item({ status: "approved" }), warnings: [] });
  document.cookie = "csrf_token=t";
  stubApi();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test("lists pending requests with lesson context", async () => {
  renderQueue();
  expect(await screen.findByRole("link", { name: "Петя Иванов" })).toHaveAttribute(
    "href",
    "/admin/families/f1",
  );
  await waitFor(() =>
    expect(screen.getByRole("link", { name: /Занятие: .*20:00–21:00/ })).toHaveAttribute(
      "href",
      "/admin/lessons/l1",
    ),
  );
  expect(screen.getByText("Перенос")).toBeInTheDocument();
  expect(screen.getByText(/в четверг после 17:00/)).toBeInTheDocument();
  expect(screen.getByText(/Болеем/)).toBeInTheDocument();
  expect(screen.getByText("Анна, 12.10.2026 13:00")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Одобрить" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Отклонить" })).toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([url]) => String(url).includes("status=pending"))).toBe(true);
});

test("shows late cancel badge", async () => {
  listResponse = () => jsonResponse(200, [item({ type: "cancel", is_late: true })]);
  renderQueue();
  expect(await screen.findByText("Поздняя отмена")).toBeInTheDocument();
});

test("shows empty state", async () => {
  listResponse = () => jsonResponse(200, []);
  renderQueue();
  expect(await screen.findByText("Запросов нет")).toBeInTheDocument();
});

test("approve reschedule sends UTC from tutor zone", async () => {
  const user = userEvent.setup();
  renderQueue();
  await user.click(await screen.findByRole("button", { name: "Одобрить" }));
  const dialog = await screen.findByRole("dialog");
  await waitFor(() => expect(within(dialog).getByRole("button", { name: "Одобрить" })).toBeEnabled());
  // предзаполнено текущим временем занятия в поясе репетитора
  expect(within(dialog).getByLabelText("Дата")).toHaveValue("2026-10-20");
  expect(within(dialog).getByLabelText("Время")).toHaveValue("20:00");
  expect(within(dialog).queryByLabelText("Длительность, мин")).not.toBeInTheDocument();
  fireEvent.change(within(dialog).getByLabelText("Дата"), { target: { value: "2026-10-21" } });
  await user.click(within(dialog).getByRole("button", { name: "Одобрить" }));
  await waitFor(() => expect(actionCalls("approve")).toHaveLength(1));
  expect(actionCalls("approve")[0]).toEqual({
    url: "/api/admin/change-requests/r1/approve",
    body: { new_starts_at: "2026-10-21T15:00:00.000Z" },
  });
  await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Запрос одобрен"));
  expect(client.invalidateQueries).toHaveBeenCalled();
});

test("approve submit is disabled until tutor zone is loaded", async () => {
  const user = userEvent.setup();
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const base = fetchMock.getMockImplementation() as (
    url: string,
    init?: RequestInit,
  ) => Promise<Response>;
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    if (url === "/api/admin/settings") await gate;
    return base(url, init);
  });
  renderQueue();
  await user.click(await screen.findByRole("button", { name: "Одобрить" }));
  const dialog = await screen.findByRole("dialog");
  expect(within(dialog).getByRole("button", { name: "Одобрить" })).toBeDisabled();
  release();
  await waitFor(() => expect(within(dialog).getByRole("button", { name: "Одобрить" })).toBeEnabled());
});

test("approve late cancel warns before confirming", async () => {
  const user = userEvent.setup();
  listResponse = () => jsonResponse(200, [item({ type: "cancel", is_late: true })]);
  actionResponse = () =>
    jsonResponse(200, {
      ...item({ type: "cancel", status: "approved" }),
      warnings: [{ message: "Пересечение с другим занятием" }],
    });
  renderQueue();
  await user.click(await screen.findByRole("button", { name: "Одобрить" }));
  const dialog = await screen.findByRole("dialog");
  expect(
    within(dialog).getByText("Отмена поздняя — занятие будет засчитано как проведённое"),
  ).toBeInTheDocument();
  expect(actionCalls("approve")).toHaveLength(0);
  await user.click(within(dialog).getByRole("button", { name: "Одобрить" }));
  await waitFor(() => expect(actionCalls("approve")).toHaveLength(1));
  expect(actionCalls("approve")[0].body).toEqual({});
  await waitFor(() => expect(toastWarning).toHaveBeenCalledWith("Пересечение с другим занятием"));
});

test("approve regular cancel says lesson will be cancelled", async () => {
  const user = userEvent.setup();
  listResponse = () => jsonResponse(200, [item({ type: "cancel" })]);
  renderQueue();
  await user.click(await screen.findByRole("button", { name: "Одобрить" }));
  expect(await screen.findByText("Занятие будет отменено")).toBeInTheDocument();
});

test("reject requires a response", async () => {
  const user = userEvent.setup();
  renderQueue();
  await user.click(await screen.findByRole("button", { name: "Отклонить" }));
  const dialog = await screen.findByRole("dialog");
  await user.click(within(dialog).getByRole("button", { name: "Отклонить" }));
  expect(await within(dialog).findByText("Напишите ответ родителю")).toBeInTheDocument();
  expect(actionCalls("reject")).toHaveLength(0);

  await user.type(within(dialog).getByLabelText("Ответ родителю"), "  Не получится  ");
  await user.click(within(dialog).getByRole("button", { name: "Отклонить" }));
  await waitFor(() => expect(actionCalls("reject")).toHaveLength(1));
  expect(actionCalls("reject")[0]).toEqual({
    url: "/api/admin/change-requests/r1/reject",
    body: { tutor_response: "Не получится" },
  });
  await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Запрос отклонён"));
});

test("outdated 409 is shown", async () => {
  const user = userEvent.setup();
  actionResponse = () =>
    jsonResponse(409, {
      error: {
        code: "change_request_outdated",
        message: "Занятие уже изменено — отклоните запрос с комментарием",
        details: {},
      },
    });
  renderQueue();
  await user.click(await screen.findByRole("button", { name: "Одобрить" }));
  const dialog = await screen.findByRole("dialog");
  await waitFor(() => expect(within(dialog).getByRole("button", { name: "Одобрить" })).toBeEnabled());
  await user.click(within(dialog).getByRole("button", { name: "Одобрить" }));
  expect(
    await within(dialog).findByText("Занятие уже изменено — отклоните запрос с комментарием"),
  ).toBeInTheDocument();
  expect(toastSuccess).not.toHaveBeenCalled();
});

test("tab all shows resolved requests without status filter", async () => {
  search = "tab=all";
  listResponse = () =>
    jsonResponse(200, [
      item({
        status: "rejected",
        tutor_response: "Не получится",
        resolved_at: "2026-10-12T09:00:00Z",
      }),
    ]);
  renderQueue();
  expect(await screen.findByText("Отклонён")).toBeInTheDocument();
  expect(screen.getByText(/Не получится/)).toBeInTheDocument();
  expect(screen.getByText("Решён 12.10.2026 14:00")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Одобрить" })).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([url]) => String(url).includes("status="))).toBe(false);
});

test("switching tabs updates the URL", async () => {
  const user = userEvent.setup();
  renderQueue();
  await screen.findByRole("link", { name: "Петя Иванов" });
  expect(screen.getByRole("tab", { name: "Ждут ответа" })).toHaveAttribute("aria-selected", "true");
  await user.click(screen.getByRole("tab", { name: "Все" }));
  expect(replace).toHaveBeenCalledWith("/admin/requests?tab=all");
});
