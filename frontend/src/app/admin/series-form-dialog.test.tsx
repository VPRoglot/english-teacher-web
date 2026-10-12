import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

import type { SeriesDetail } from "@/api/generated/model";

import { SeriesFormDialog } from "./series-form-dialog";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const SAVED = {
  lessons_created: 16,
  warnings: [] as unknown[],
  series: {
    id: "s1",
    child_id: "c1",
    child_name: "Петя",
    rrule: "FREQ=WEEKLY;BYDAY=TU,FR",
    local_start_time: "18:00:00",
    duration_min: 60,
    meeting_url: null,
    starts_on: "2026-10-12",
    ends_on: null,
    archived_at: null,
  },
};

let fetchMock: ReturnType<typeof vi.fn>;
let postResponse: () => Response;
let client: QueryClient;
const onSaved = vi.fn();
const onOpenChange = vi.fn();

function stubApi() {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/admin/settings") {
      return jsonResponse(200, { timezone: "Europe/Moscow", cancel_policy_hours: 24 });
    }
    if (url === "/api/admin/series" && init?.method === "POST") return postResponse();
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function posts(): unknown[] {
  return fetchMock.mock.calls
    .filter(([url, init]) => url === "/api/admin/series" && init?.method === "POST")
    .map(([, init]) => JSON.parse((init as RequestInit).body as string));
}

function renderDialog(props: Partial<React.ComponentProps<typeof SeriesFormDialog>> = {}) {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.spyOn(client, "invalidateQueries");
  return render(
    <QueryClientProvider client={client}>
      <SeriesFormDialog
        mode="create"
        childId="c1"
        open
        onOpenChange={onOpenChange}
        onSaved={onSaved}
        {...props}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  toastSuccess.mockReset();
  toastWarning.mockReset();
  onSaved.mockReset();
  onOpenChange.mockReset();
  postResponse = () => jsonResponse(201, SAVED);
  document.cookie = "csrf_token=t";
  stubApi();
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test("creates weekly series with canonical rule", async () => {
  const user = userEvent.setup();
  renderDialog();

  await user.click(await screen.findByRole("checkbox", { name: "пт" }));
  await user.click(screen.getByRole("checkbox", { name: "вт" }));
  fireEvent.change(screen.getByLabelText("Время"), { target: { value: "18:00" } });
  fireEvent.change(screen.getByLabelText("Начало"), { target: { value: "2026-10-12" } });
  await user.click(screen.getByRole("button", { name: "Создать" }));

  await waitFor(() => expect(posts()).toHaveLength(1));
  expect(posts()[0]).toEqual({
    child_id: "c1",
    rrule: "FREQ=WEEKLY;BYDAY=TU,FR",
    local_start_time: "18:00",
    duration_min: 60,
    starts_on: "2026-10-12",
  });
  await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Расписание создано: 16 занятий"));
  expect(client.invalidateQueries).toHaveBeenCalledWith({ queryKey: ["/api/admin/lessons"] });
  expect(onSaved).toHaveBeenCalledTimes(1);
});

test("sends the interval, end date and link when they are filled", async () => {
  const user = userEvent.setup();
  renderDialog();

  await user.click(await screen.findByRole("checkbox", { name: "пн" }));
  await user.selectOptions(screen.getByLabelText("Повтор"), "2");
  fireEvent.change(screen.getByLabelText("Время"), { target: { value: "10:05" } });
  fireEvent.change(screen.getByLabelText("Начало"), { target: { value: "2026-10-12" } });
  fireEvent.change(screen.getByLabelText("Окончание"), { target: { value: "2026-12-28" } });
  await user.type(screen.getByLabelText("Ссылка на занятие"), "https://meet.example.com/a");
  await user.click(screen.getByRole("button", { name: "Создать" }));

  await waitFor(() => expect(posts()).toHaveLength(1));
  expect(posts()[0]).toEqual({
    child_id: "c1",
    rrule: "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO",
    local_start_time: "10:05",
    duration_min: 60,
    starts_on: "2026-10-12",
    ends_on: "2026-12-28",
    meeting_url: "https://meet.example.com/a",
  });
});

test("requires at least one weekday", async () => {
  const user = userEvent.setup();
  renderDialog();

  fireEvent.change(await screen.findByLabelText("Время"), { target: { value: "18:00" } });
  fireEvent.change(screen.getByLabelText("Начало"), { target: { value: "2026-10-12" } });
  await user.click(screen.getByRole("button", { name: "Создать" }));

  expect(await screen.findByText("Выберите дни недели")).toBeInTheDocument();
  expect(posts()).toHaveLength(0);
});

test("rejects an end date before the start date", async () => {
  const user = userEvent.setup();
  renderDialog();

  await user.click(await screen.findByRole("checkbox", { name: "вт" }));
  fireEvent.change(screen.getByLabelText("Время"), { target: { value: "18:00" } });
  fireEvent.change(screen.getByLabelText("Начало"), { target: { value: "2026-10-12" } });
  fireEvent.change(screen.getByLabelText("Окончание"), { target: { value: "2026-10-01" } });
  await user.click(screen.getByRole("button", { name: "Создать" }));

  expect(await screen.findByText("Окончание не может быть раньше начала")).toBeInTheDocument();
  expect(posts()).toHaveLength(0);
});

test("prefills the weekday, time and start date from the clicked slot", async () => {
  renderDialog({ initial: { date: "2026-10-20", time: "18:00" } });

  expect(await screen.findByRole("checkbox", { name: "вт" })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "пн" })).not.toBeChecked();
  expect(screen.getByLabelText("Время")).toHaveValue("18:00");
  expect(screen.getByLabelText("Начало")).toHaveValue("2026-10-20");
});

test("overlap warnings become separate toasts", async () => {
  postResponse = () =>
    jsonResponse(201, {
      ...SAVED,
      lessons_created: 1,
      warnings: [
        { code: "overlap", lesson_id: "l1", starts_at: "2026-10-13T15:00:00Z", message: "Пересечение A" },
        { code: "overlap", lesson_id: "l2", starts_at: "2026-10-16T15:00:00Z", message: "Пересечение B" },
      ],
    });
  const user = userEvent.setup();
  renderDialog({ initial: { date: "2026-10-20", time: "18:00" } });

  await user.click(await screen.findByRole("button", { name: "Создать" }));

  await waitFor(() => expect(toastWarning).toHaveBeenCalledTimes(2));
  expect(toastWarning).toHaveBeenNthCalledWith(1, "Пересечение A");
  expect(toastWarning).toHaveBeenNthCalledWith(2, "Пересечение B");
  expect(toastSuccess).toHaveBeenCalledWith("Расписание создано: 1 занятие");
});

test("shows an API error in the form and keeps the dialog open", async () => {
  postResponse = () =>
    jsonResponse(409, { error: { code: "child_archived", message: "Ученик в архиве", details: {} } });
  const user = userEvent.setup();
  renderDialog({ initial: { date: "2026-10-20", time: "18:00" } });

  await user.click(await screen.findByRole("button", { name: "Создать" }));

  expect(await screen.findByText("Ученик в архиве")).toBeInTheDocument();
  expect(onSaved).not.toHaveBeenCalled();
  expect(toastSuccess).not.toHaveBeenCalled();
});

test("puts a 422 field error on the field", async () => {
  postResponse = () =>
    jsonResponse(422, {
      error: {
        code: "validation_error",
        message: "Ошибка",
        details: { fields: [{ loc: ["body", "meeting_url"], message: "Некорректная ссылка" }] },
      },
    });
  const user = userEvent.setup();
  renderDialog({ initial: { date: "2026-10-20", time: "18:00" } });

  await user.click(await screen.findByRole("button", { name: "Создать" }));

  expect(await screen.findByText("Некорректная ссылка")).toBeInTheDocument();
});

test("edit mode asks for the date to change from instead of the start date", async () => {
  const series: SeriesDetail = {
    ...SAVED.series,
    rrule: "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE",
    local_start_time: "17:30:00",
    duration_min: 45,
    meeting_url: "https://meet.example.com/x",
    ends_on: "2026-12-01",
  };
  const onEditSubmit = vi.fn();
  const user = userEvent.setup();
  renderDialog({ mode: "edit", series, onEditSubmit });

  expect(await screen.findByLabelText("Изменить начиная с")).toBeInTheDocument();
  expect(screen.queryByLabelText("Начало")).not.toBeInTheDocument();
  expect(screen.getByRole("checkbox", { name: "пн" })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "ср" })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "вт" })).not.toBeChecked();
  expect(screen.getByLabelText("Повтор")).toHaveValue("2");
  expect(screen.getByLabelText("Время")).toHaveValue("17:30");
  expect(screen.getByLabelText("Длительность, мин")).toHaveValue(45);
  expect(screen.getByLabelText("Ссылка на занятие")).toHaveValue("https://meet.example.com/x");
  expect(screen.getByLabelText("Окончание")).toHaveValue("2026-12-01");

  fireEvent.change(screen.getByLabelText("Изменить начиная с"), { target: { value: "2026-11-02" } });
  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  await waitFor(() => expect(onEditSubmit).toHaveBeenCalledTimes(1));
  expect(onEditSubmit.mock.calls[0]?.[0]).toMatchObject({
    from: "2026-11-02",
    rrule: "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE",
    local_start_time: "17:30",
    duration_min: 45,
    meeting_url: "https://meet.example.com/x",
    ends_on: "2026-12-01",
  });
  expect(posts()).toHaveLength(0);
});
