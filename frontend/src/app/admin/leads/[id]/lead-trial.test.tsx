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

import { getListLeadsQueryKey } from "@/api/generated/endpoints/admin/admin";
import type { LeadStatus } from "@/api/generated/model";

import { bodyOf, errorResponse, jsonResponse, makeLead } from "./lead-fixture";
import { LeadTrial } from "./lead-trial";

const TRIAL_URL = "/api/admin/leads/l1/trial";
const TRIALS_URL = "/api/admin/leads/l1/trial-lessons";

const STUDENT = {
  child_id: null,
  lead_id: "l1",
  name: "Маша",
  family_id: null,
  family_name: null,
};

function trialLesson(overrides: Record<string, unknown> = {}) {
  return {
    id: "t1",
    duration_min: 30,
    has_notes: false,
    is_detached: false,
    join_url: null,
    kind: "trial",
    meeting_url: null,
    series_id: null,
    starts_at: "2026-10-20T15:00:00Z",
    status: "scheduled",
    student: STUDENT,
    ...overrides,
  };
}

function saved(warnings: unknown[] = []) {
  return {
    ...trialLesson(),
    created_at: "2026-10-12T10:00:00Z",
    notes: { shared_text: "", private_text: "" },
    warnings,
  };
}

let trials: unknown[];
let trialResponse: () => Response;
let settingsFail: boolean;
let fetchMock: ReturnType<typeof vi.fn>;
let client: QueryClient;

function schedules() {
  return fetchMock.mock.calls.filter(([url, init]) => url === TRIAL_URL && init?.method === "POST");
}

function renderTrial(status: LeadStatus = "new") {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.spyOn(client, "invalidateQueries");
  return render(
    <QueryClientProvider client={client}>
      <LeadTrial lead={makeLead({ status })} />
    </QueryClientProvider>,
  );
}

/** Открывает диалог и ждёт пояс репетитора: до этого отправка заблокирована. */
async function openDialog() {
  await userEvent.click(await screen.findByRole("button", { name: "Назначить пробное" }));
  const dialog = await screen.findByRole("dialog");
  await waitFor(() => expect(within(dialog).getByRole("button", { name: "Назначить" })).toBeEnabled());
  return dialog;
}

beforeEach(() => {
  toastSuccess.mockReset();
  toastWarning.mockReset();
  document.cookie = "csrf_token=t";
  trials = [];
  settingsFail = false;
  trialResponse = () => jsonResponse(201, saved());
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/admin/settings") {
      if (settingsFail) return errorResponse(500, "boom", "Сбой");
      return jsonResponse(200, { timezone: "Europe/Moscow", cancel_policy_hours: 24 });
    }
    if (url === TRIALS_URL && init?.method === "GET") return jsonResponse(200, trials);
    if (url === TRIAL_URL && init?.method === "POST") return trialResponse();
    throw new Error(`unexpected fetch ${init?.method} ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test.each([
  ["new", true],
  ["contacted", true],
  ["trial_scheduled", false],
  ["converted", false],
  ["rejected", false],
] as const)("status %s shows the schedule button: %s", async (status, visible) => {
  renderTrial(status);
  expect(await screen.findByRole("heading", { name: "Пробное занятие" })).toBeInTheDocument();
  const button = screen.queryByRole("button", { name: "Назначить пробное" });
  if (visible) expect(button).toBeInTheDocument();
  else expect(button).not.toBeInTheDocument();
});

test("lists trial lessons with time, status and a link", async () => {
  trials = [
    trialLesson(),
    trialLesson({ id: "t2", starts_at: "2026-10-13T07:00:00Z", status: "cancelled" }),
  ];
  renderTrial("trial_scheduled");

  const items = await screen.findAllByRole("listitem");
  expect(items).toHaveLength(2);
  expect(within(items[0]).getByText("вт, 20 окт., 18:00–18:30")).toBeInTheDocument();
  expect(within(items[0]).getByText("Запланировано")).toBeInTheDocument();
  expect(within(items[0]).getByRole("link", { name: "Открыть" })).toHaveAttribute(
    "href",
    "/admin/lessons/t1",
  );
  expect(within(items[1]).getByText("вт, 13 окт., 10:00–10:30")).toBeInTheDocument();
  expect(within(items[1]).getByText("Отменено")).toBeInTheDocument();
  expect(within(items[1]).getByRole("link", { name: "Открыть" })).toHaveAttribute(
    "href",
    "/admin/lessons/t2",
  );
});

test("says so when there are no trial lessons", async () => {
  renderTrial("new");
  expect(await screen.findByText("Пробных занятий пока нет")).toBeInTheDocument();
});

test("schedules a trial in the tutor zone and refreshes the lead", async () => {
  renderTrial("new");
  const dialog = await openDialog();

  expect(within(dialog).getByLabelText("Длительность, мин")).toHaveValue(30);
  fireEvent.change(within(dialog).getByLabelText("Дата"), { target: { value: "2026-10-20" } });
  fireEvent.change(within(dialog).getByLabelText("Время"), { target: { value: "18:00" } });
  await userEvent.click(within(dialog).getByRole("button", { name: "Назначить" }));

  await waitFor(() => expect(schedules()).toHaveLength(1));
  expect(bodyOf(schedules()[0])).toEqual({
    starts_at: "2026-10-20T15:00:00.000Z",
    duration_min: 30,
  });
  await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Пробное занятие назначено"));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  for (const queryKey of [["/api/admin/leads/l1"], getListLeadsQueryKey()]) {
    expect(client.invalidateQueries).toHaveBeenCalledWith({ queryKey });
  }
  // Списки занятий, серии и пробные занятия заявки — одним предикатом расписания.
  const predicate = vi
    .mocked(client.invalidateQueries)
    .mock.calls.map(([filters]) => filters?.predicate)
    .find((candidate) => candidate !== undefined);
  expect(predicate).toBeDefined();
  expect(predicate?.({ queryKey: [TRIALS_URL] } as never)).toBe(true);
  expect(predicate?.({ queryKey: ["/api/admin/lessons", {}] } as never)).toBe(true);
  expect(predicate?.({ queryKey: ["/api/admin/leads/l1"] } as never)).toBe(false);
});

test("sends the meeting link and a changed duration", async () => {
  renderTrial("contacted");
  const dialog = await openDialog();

  fireEvent.change(within(dialog).getByLabelText("Дата"), { target: { value: "2026-10-20" } });
  fireEvent.change(within(dialog).getByLabelText("Время"), { target: { value: "18:00" } });
  fireEvent.change(within(dialog).getByLabelText("Длительность, мин"), { target: { value: "45" } });
  await userEvent.type(within(dialog).getByLabelText("Ссылка на занятие"), "https://meet.example.com/a");
  await userEvent.click(within(dialog).getByRole("button", { name: "Назначить" }));

  await waitFor(() => expect(schedules()).toHaveLength(1));
  expect(bodyOf(schedules()[0])).toEqual({
    starts_at: "2026-10-20T15:00:00.000Z",
    duration_min: 45,
    meeting_url: "https://meet.example.com/a",
  });
});

test("overlap warnings become toasts", async () => {
  trialResponse = () =>
    jsonResponse(
      201,
      saved([
        {
          code: "overlap",
          lesson_id: "l9",
          starts_at: "2026-10-20T15:00:00Z",
          message: "Пересекается с занятием Петя в 18:00",
        },
      ]),
    );
  renderTrial("new");
  const dialog = await openDialog();
  await userEvent.click(within(dialog).getByRole("button", { name: "Назначить" }));

  await waitFor(() =>
    expect(toastWarning).toHaveBeenCalledWith("Пересекается с занятием Петя в 18:00"),
  );
  expect(toastSuccess).toHaveBeenCalledWith("Пробное занятие назначено");
});

test("a 409 is shown in the dialog and the lead is refreshed", async () => {
  trialResponse = () =>
    errorResponse(409, "invalid_status_transition", "Из этого статуса пробное назначить нельзя");
  renderTrial("new");
  const dialog = await openDialog();
  await userEvent.click(within(dialog).getByRole("button", { name: "Назначить" }));

  expect(await within(dialog).findByRole("alert")).toHaveTextContent(
    "Из этого статуса пробное назначить нельзя",
  );
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(toastSuccess).not.toHaveBeenCalled();
  expect(client.invalidateQueries).toHaveBeenCalledWith({ queryKey: ["/api/admin/leads/l1"] });
});

test("client validation blocks the request", async () => {
  renderTrial("new");
  const dialog = await openDialog();
  fireEvent.change(within(dialog).getByLabelText("Длительность, мин"), { target: { value: "10" } });
  await userEvent.click(within(dialog).getByRole("button", { name: "Назначить" }));

  expect(await within(dialog).findByText("Не менее 15 минут")).toBeInTheDocument();
  expect(schedules()).toHaveLength(0);
});

test("the trial form shows the settings load error and has no submit", async () => {
  settingsFail = true;
  renderTrial("new");
  await userEvent.click(await screen.findByRole("button", { name: "Назначить пробное" }));
  const dialog = await screen.findByRole("dialog");

  expect(
    await within(dialog).findByText("Не удалось загрузить настройки репетитора. Обновите страницу."),
  ).toBeInTheDocument();
  expect(within(dialog).queryByRole("button", { name: "Назначить" })).not.toBeInTheDocument();
  expect(schedules()).toHaveLength(0);
});

test("the form starts clean after being closed", async () => {
  renderTrial("new");
  const dialog = await openDialog();
  await userEvent.type(within(dialog).getByLabelText("Ссылка на занятие"), "https://meet.example.com/a");
  await userEvent.click(within(dialog).getByRole("button", { name: "Отмена" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

  await openDialog();
  expect(screen.getByLabelText("Ссылка на занятие")).toHaveValue("");
});
