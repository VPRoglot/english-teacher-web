import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { LessonForFamilyDetail } from "@/api/generated/model";

const toastSuccess = vi.hoisted(() => vi.fn());
vi.mock("sonner", () => ({ toast: { success: toastSuccess, warning: vi.fn(), error: vi.fn() } }));

import { ChangeRequestDialog } from "./change-request-dialog";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
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

let postResponse: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-12T09:00:00Z"));
  document.cookie = "csrf_token=t";
  toastSuccess.mockClear();
  postResponse = () => jsonResponse(201, { id: "r1" });
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/me/schedule-settings") {
      return jsonResponse(200, { timezone: "Europe/Moscow", cancel_policy_hours: 24 });
    }
    if (url === "/api/me/lessons/l1/change-requests" && init?.method === "POST") {
      return postResponse();
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

function renderDialog(type: "reschedule" | "cancel", lesson = makeLesson()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onOpenChange = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <ChangeRequestDialog type={type} lesson={lesson} open onOpenChange={onOpenChange} />
    </QueryClientProvider>,
  );
  return { onOpenChange };
}

function postCalls() {
  return fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
}

async function enabledSubmit() {
  const button = screen.getByRole("button", { name: "Отправить" });
  await waitFor(() => expect(button).toBeEnabled());
  return button;
}

test("submit is disabled until schedule settings are loaded", async () => {
  let release: (response: Response) => void = () => {};
  const pending = new Promise<Response>((resolve) => {
    release = resolve;
  });
  const base = fetchMock.getMockImplementation()!;
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) =>
    url === "/api/me/schedule-settings" ? pending : base(url, init),
  );
  renderDialog("cancel", makeLesson({ starts_at: "2026-10-12T19:00:00Z" }));
  const button = screen.getByRole("button", { name: "Отправить" });
  expect(button).toBeDisabled();
  release(jsonResponse(200, { timezone: "Europe/Moscow", cancel_policy_hours: 24 }));
  await waitFor(() => expect(button).toBeEnabled());
  expect(screen.getByText(/До занятия меньше 24 ч/)).toBeInTheDocument();
});

test("settings error blocks submit and shows an alert", async () => {
  const base = fetchMock.getMockImplementation()!;
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) =>
    url === "/api/me/schedule-settings"
      ? jsonResponse(500, { error: { code: "internal", message: "Ошибка", details: {} } })
      : base(url, init),
  );
  renderDialog("cancel");
  expect(
    await screen.findByText("Не удалось загрузить настройки. Обновите страницу."),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Отправить" })).toBeDisabled();
  expect(postCalls()).toHaveLength(0);
});

test("cancel within policy shows late warning", async () => {
  renderDialog("cancel", makeLesson({ starts_at: "2026-10-12T19:00:00Z" })); // через 10 ч
  expect(
    await screen.findByText(
      "До занятия меньше 24 ч — отмена будет засчитана как проведённое занятие",
    ),
  ).toBeInTheDocument();
});

test("reschedule within policy shows its own warning", async () => {
  renderDialog("reschedule", makeLesson({ starts_at: "2026-10-12T19:00:00Z" }));
  expect(
    await screen.findByText(
      "Если перенос не согласуют, занятие может быть засчитано как проведённое",
    ),
  ).toBeInTheDocument();
});

test("no warning when far from the lesson", async () => {
  renderDialog("cancel");
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith("/api/me/schedule-settings", expect.anything()),
  );
  await new Promise((r) => setTimeout(r, 30));
  expect(screen.queryByText(/До занятия меньше/)).not.toBeInTheDocument();
});

test("reschedule requires proposed time", async () => {
  const user = userEvent.setup();
  renderDialog("reschedule");
  await user.click(await enabledSubmit());
  expect(await screen.findByText("Укажите удобное время")).toBeInTheDocument();
  expect(postCalls()).toHaveLength(0);
});

test("sends request and shows toast", async () => {
  const user = userEvent.setup();
  const { onOpenChange } = renderDialog("cancel");
  await user.type(screen.getByLabelText("Комментарий"), "Болеем");
  await user.click(await enabledSubmit());
  await waitFor(() => expect(postCalls()).toHaveLength(1));
  expect(JSON.parse(postCalls()[0][1].body)).toEqual({ type: "cancel", comment: "Болеем" });
  await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Запрос отправлен репетитору"));
  expect(onOpenChange).toHaveBeenCalledWith(false);
});

test("reschedule sends proposed text", async () => {
  const user = userEvent.setup();
  renderDialog("reschedule");
  await user.type(screen.getByLabelText("Когда удобно?"), "в четверг");
  await user.click(await enabledSubmit());
  await waitFor(() => expect(postCalls()).toHaveLength(1));
  expect(JSON.parse(postCalls()[0][1].body)).toEqual({
    type: "reschedule",
    proposed_text: "в четверг",
  });
});

test("409 is shown", async () => {
  postResponse = () =>
    jsonResponse(409, {
      error: {
        code: "change_request_exists",
        message: "Запрос по этому занятию уже есть",
        details: {},
      },
    });
  const user = userEvent.setup();
  const { onOpenChange } = renderDialog("cancel");
  await user.click(await enabledSubmit());
  expect(await screen.findByText("Запрос по этому занятию уже есть")).toBeInTheDocument();
  expect(onOpenChange).not.toHaveBeenCalledWith(false);
  expect(toastSuccess).not.toHaveBeenCalled();
});
