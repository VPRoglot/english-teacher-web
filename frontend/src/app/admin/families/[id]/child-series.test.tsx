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

import { getListSeriesQueryKey } from "@/api/generated/endpoints/admin/admin";
import type { ChildDetail, SeriesDetail } from "@/api/generated/model";

import { ChildSeries } from "./child-series";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const CHILD: ChildDetail = {
  id: "c1",
  full_name: "Петя",
  birth_year: 2015,
  english_level: "A2",
  default_meeting_url: null,
  archived_at: null,
  account: null,
};

const SERIES: SeriesDetail = {
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
};

const SAVED = {
  series: SERIES,
  lessons_created: 2,
  lessons_updated: 6,
  lessons_removed: 1,
  warnings: [] as unknown[],
};

let seriesList: SeriesDetail[];
let routes: Record<string, () => Response>;
let settingsResponse: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
let client: QueryClient;

function stubApi() {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url}`;
    if (key === "GET /api/admin/series?child_id=c1") return jsonResponse(200, seriesList);
    if (key === "GET /api/admin/settings") return settingsResponse();
    const handler = routes[key];
    if (!handler) throw new Error(`unexpected fetch ${key}`);
    return handler();
  });
  vi.stubGlobal("fetch", fetchMock);
}

function calls(method: string, url: string) {
  return fetchMock.mock.calls.filter(([u, init]) => u === url && init?.method === method);
}

function bodyOf(call: unknown[] | undefined): unknown {
  return JSON.parse(String((call?.[1] as RequestInit | undefined)?.body));
}

function renderBlock() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.spyOn(client, "invalidateQueries");
  return render(
    <QueryClientProvider client={client}>
      <ChildSeries child={CHILD} />
    </QueryClientProvider>,
  );
}

/** Строка серии и готовый к отправке диалог (пояс репетитора загружен). */
async function openEdit(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Изменить расписание" }));
  const dialog = await screen.findByRole("dialog");
  await waitFor(() => expect(within(dialog).getByRole("button", { name: "Сохранить" })).toBeEnabled());
  return dialog;
}

beforeEach(() => {
  // Фильтр списка зависит от сегодняшней даты: замораживаем только `Date`, таймеры настоящие.
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-12T09:00:00Z"));
  toastSuccess.mockReset();
  toastWarning.mockReset();
  seriesList = [SERIES];
  routes = {};
  settingsResponse = () =>
    jsonResponse(200, { timezone: "Europe/Moscow", cancel_policy_hours: 24 });
  document.cookie = "csrf_token=t";
  stubApi();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test("lists active series with description and dates", async () => {
  seriesList = [
    SERIES,
    {
      ...SERIES,
      id: "s2",
      rrule: "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO",
      local_start_time: "10:00:00",
      duration_min: 45,
      starts_on: "2026-11-02",
      ends_on: "2026-12-28",
    },
  ];
  renderBlock();

  expect(await screen.findByRole("heading", { name: "Расписание" })).toBeInTheDocument();
  const rows = await screen.findAllByRole("listitem");
  expect(rows).toHaveLength(2);
  expect(within(rows[0]!).getByText("по вт и пт в 18:00, 60 мин")).toBeInTheDocument();
  expect(within(rows[0]!).getByText("с 12.10.2026")).toBeInTheDocument();
  expect(within(rows[0]!).queryByText(/^по \d/)).not.toBeInTheDocument();
  expect(within(rows[1]!).getByText("раз в 2 недели по пн в 10:00, 45 мин")).toBeInTheDocument();
  expect(within(rows[1]!).getByText("с 02.11.2026")).toBeInTheDocument();
  expect(within(rows[1]!).getByText("по 28.12.2026")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Добавить расписание" })).toBeInTheDocument();
});

test("shows the empty state", async () => {
  seriesList = [];
  renderBlock();
  expect(await screen.findByText("Регулярных занятий нет")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Добавить расписание" })).toBeInTheDocument();
});

test("hides a series whose end date has passed", async () => {
  seriesList = [{ ...SERIES, id: "old", ends_on: "2020-01-31" }];
  renderBlock();
  expect(await screen.findByText("Регулярных занятий нет")).toBeInTheDocument();
});

test("shows a load error", async () => {
  fetchMock.mockImplementation(async (url: string) => {
    if (url === "/api/admin/series?child_id=c1") {
      return jsonResponse(500, { error: { code: "boom", message: "Сбой сервера", details: {} } });
    }
    return settingsResponse();
  });
  renderBlock();
  expect(await screen.findByText("Сбой сервера")).toBeInTheDocument();
});

test("add opens the create form for this child", async () => {
  seriesList = [];
  routes["POST /api/admin/series"] = () => jsonResponse(201, SAVED);
  const user = userEvent.setup();
  renderBlock();

  await user.click(await screen.findByRole("button", { name: "Добавить расписание" }));
  const dialog = await screen.findByRole("dialog");
  const create = within(dialog).getByRole("button", { name: "Создать" });
  await waitFor(() => expect(create).toBeEnabled());
  await user.click(within(dialog).getByRole("checkbox", { name: "вт" }));
  fireEvent.change(within(dialog).getByLabelText("Время"), { target: { value: "18:00" } });
  fireEvent.change(within(dialog).getByLabelText("Начало"), { target: { value: "2026-10-20" } });
  await user.click(create);

  await waitFor(() => expect(calls("POST", "/api/admin/series")).toHaveLength(1));
  expect(bodyOf(calls("POST", "/api/admin/series")[0])).toMatchObject({
    child_id: "c1",
    rrule: "FREQ=WEEKLY;BYDAY=TU",
  });
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

test("edit sends this_and_following with the from date and changed fields only", async () => {
  const url = "/api/admin/series/s1?scope=this_and_following&from=2026-10-20";
  routes[`PATCH ${url}`] = () => jsonResponse(200, SAVED);
  const user = userEvent.setup();
  renderBlock();
  const dialog = await openEdit(user);

  // Prefilled from the series.
  expect(within(dialog).getByRole("checkbox", { name: "вт" })).toBeChecked();
  expect(within(dialog).getByRole("checkbox", { name: "пт" })).toBeChecked();
  expect(within(dialog).getByLabelText("Время")).toHaveValue("18:00");

  fireEvent.change(within(dialog).getByLabelText("Время"), { target: { value: "19:00" } });
  fireEvent.change(within(dialog).getByLabelText("Изменить начиная с"), {
    target: { value: "2026-10-20" },
  });
  await user.click(within(dialog).getByRole("button", { name: "Сохранить" }));

  await waitFor(() => expect(calls("PATCH", url)).toHaveLength(1));
  expect(bodyOf(calls("PATCH", url)[0])).toEqual({ local_start_time: "19:00" });
  await waitFor(() =>
    expect(toastSuccess).toHaveBeenCalledWith(
      "Расписание изменено: обновлено 6 занятий, добавлено 2, удалено 1",
    ),
  );
  expect(client.invalidateQueries).toHaveBeenCalledWith({ predicate: expect.any(Function) });
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

test("the edit toast leaves out zero counts", async () => {
  const url = "/api/admin/series/s1?scope=this_and_following&from=2026-10-20";
  routes[`PATCH ${url}`] = () =>
    jsonResponse(200, { ...SAVED, lessons_created: 0, lessons_updated: 3, lessons_removed: 0 });
  const user = userEvent.setup();
  renderBlock();
  const dialog = await openEdit(user);

  fireEvent.change(within(dialog).getByLabelText("Время"), { target: { value: "19:00" } });
  fireEvent.change(within(dialog).getByLabelText("Изменить начиная с"), {
    target: { value: "2026-10-20" },
  });
  await user.click(within(dialog).getByRole("button", { name: "Сохранить" }));

  await waitFor(() =>
    expect(toastSuccess).toHaveBeenCalledWith("Расписание изменено: обновлено 3 занятия"),
  );
  expect(toastSuccess.mock.calls[0]?.[0]).not.toMatch(/\b0\b/);
});

test("edit can clear the link and the end date, and change days and interval", async () => {
  seriesList = [{ ...SERIES, meeting_url: "https://meet.example.com/x", ends_on: "2026-12-28" }];
  const url = "/api/admin/series/s1?scope=this_and_following&from=2026-10-20";
  routes[`PATCH ${url}`] = () => jsonResponse(200, SAVED);
  const user = userEvent.setup();
  renderBlock();
  const dialog = await openEdit(user);

  await user.click(within(dialog).getByRole("checkbox", { name: "пт" }));
  await user.click(within(dialog).getByRole("checkbox", { name: "ср" }));
  await user.selectOptions(within(dialog).getByLabelText("Повтор"), "2");
  fireEvent.change(within(dialog).getByLabelText("Длительность, мин"), { target: { value: "45" } });
  await user.clear(within(dialog).getByLabelText("Ссылка на занятие"));
  fireEvent.change(within(dialog).getByLabelText("Окончание"), { target: { value: "" } });
  fireEvent.change(within(dialog).getByLabelText("Изменить начиная с"), {
    target: { value: "2026-10-20" },
  });
  await user.click(within(dialog).getByRole("button", { name: "Сохранить" }));

  await waitFor(() => expect(calls("PATCH", url)).toHaveLength(1));
  expect(bodyOf(calls("PATCH", url)[0])).toEqual({
    rrule: "FREQ=WEEKLY;INTERVAL=2;BYDAY=TU,WE",
    duration_min: 45,
    meeting_url: null,
    ends_on: null,
  });
});

test("edit without changes sends nothing and closes the dialog", async () => {
  const user = userEvent.setup();
  renderBlock();
  const dialog = await openEdit(user);

  await user.click(within(dialog).getByRole("button", { name: "Сохранить" }));

  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(false);
});

test("overlap warnings from the edit become toasts", async () => {
  const url = "/api/admin/series/s1?scope=this_and_following&from=2026-10-20";
  routes[`PATCH ${url}`] = () =>
    jsonResponse(200, {
      ...SAVED,
      warnings: [
        { code: "overlap", lesson_id: "l1", starts_at: "2026-10-20T15:00:00Z", message: "Пересечение A" },
      ],
    });
  const user = userEvent.setup();
  renderBlock();
  const dialog = await openEdit(user);

  fireEvent.change(within(dialog).getByLabelText("Время"), { target: { value: "19:00" } });
  fireEvent.change(within(dialog).getByLabelText("Изменить начиная с"), {
    target: { value: "2026-10-20" },
  });
  await user.click(within(dialog).getByRole("button", { name: "Сохранить" }));

  await waitFor(() => expect(toastWarning).toHaveBeenCalledWith("Пересечение A"));
});

test("422 on from is shown under the field", async () => {
  const url = "/api/admin/series/s1?scope=this_and_following&from=2026-10-01";
  routes[`PATCH ${url}`] = () =>
    jsonResponse(422, {
      error: {
        code: "validation_error",
        message: "Ошибка",
        details: {
          fields: [{ loc: ["query", "from"], message: "Дата изменения не может быть в прошлом" }],
        },
      },
    });
  const user = userEvent.setup();
  renderBlock();
  const dialog = await openEdit(user);

  fireEvent.change(within(dialog).getByLabelText("Время"), { target: { value: "19:00" } });
  fireEvent.change(within(dialog).getByLabelText("Изменить начиная с"), {
    target: { value: "2026-10-01" },
  });
  await user.click(within(dialog).getByRole("button", { name: "Сохранить" }));

  const message = await within(dialog).findByText("Дата изменения не может быть в прошлом");
  expect(message.closest("div")).toContainElement(within(dialog).getByLabelText("Изменить начиная с"));
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(toastSuccess).not.toHaveBeenCalled();
});

test("422 on the end date is shown under the end date field", async () => {
  const url = "/api/admin/series/s1?scope=this_and_following&from=2026-10-20";
  routes[`PATCH ${url}`] = () =>
    jsonResponse(422, {
      error: {
        code: "validation_error",
        message: "Ошибка",
        details: { fields: [{ loc: ["body", "ends_on"], message: "Окончание раньше начала" }] },
      },
    });
  const user = userEvent.setup();
  renderBlock();
  const dialog = await openEdit(user);

  fireEvent.change(within(dialog).getByLabelText("Время"), { target: { value: "19:00" } });
  fireEvent.change(within(dialog).getByLabelText("Изменить начиная с"), {
    target: { value: "2026-10-20" },
  });
  await user.click(within(dialog).getByRole("button", { name: "Сохранить" }));

  expect(await within(dialog).findByText("Окончание раньше начала")).toBeInTheDocument();
});

test("409 series_archived is shown in the dialog", async () => {
  const url = "/api/admin/series/s1?scope=this_and_following&from=2026-10-20";
  routes[`PATCH ${url}`] = () =>
    jsonResponse(409, {
      error: { code: "series_archived", message: "Расписание уже завершено", details: {} },
    });
  const user = userEvent.setup();
  renderBlock();
  const dialog = await openEdit(user);

  fireEvent.change(within(dialog).getByLabelText("Время"), { target: { value: "19:00" } });
  fireEvent.change(within(dialog).getByLabelText("Изменить начиная с"), {
    target: { value: "2026-10-20" },
  });
  await user.click(within(dialog).getByRole("button", { name: "Сохранить" }));

  expect(await within(dialog).findByText("Расписание уже завершено")).toBeInTheDocument();
  expect(toastSuccess).not.toHaveBeenCalled();
});

test("the edit submit is disabled while the request is in flight", async () => {
  const url = "/api/admin/series/s1?scope=this_and_following&from=2026-10-20";
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  fetchMock.mockImplementation(async (u: string, init?: RequestInit) => {
    if (u === "/api/admin/series?child_id=c1") return jsonResponse(200, seriesList);
    if (u === "/api/admin/settings") return settingsResponse();
    if (init?.method === "PATCH" && u === url) {
      await gate;
      return jsonResponse(200, SAVED);
    }
    throw new Error(`unexpected fetch ${u}`);
  });
  const user = userEvent.setup();
  renderBlock();
  const dialog = await openEdit(user);

  fireEvent.change(within(dialog).getByLabelText("Время"), { target: { value: "19:00" } });
  fireEvent.change(within(dialog).getByLabelText("Изменить начиная с"), {
    target: { value: "2026-10-20" },
  });
  await user.click(within(dialog).getByRole("button", { name: "Сохранить" }));

  expect(await within(dialog).findByRole("button", { name: "Сохраняем…" })).toBeDisabled();
  release();
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(calls("PATCH", url)).toHaveLength(1);
});

test("the list waits for the tutor time zone and does not filter by the fallback zone", async () => {
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  // Ends "today" in the real zone (Pago Pago, UTC-11), already yesterday in the fallback Moscow.
  seriesList = [{ ...SERIES, id: "edge", ends_on: "2026-10-11" }, { ...SERIES, id: "open" }];
  fetchMock.mockImplementation(async (url: string) => {
    if (url === "/api/admin/series?child_id=c1") return jsonResponse(200, seriesList);
    if (url === "/api/admin/settings") {
      await gate;
      return jsonResponse(200, { timezone: "Pacific/Pago_Pago", cancel_policy_hours: 24 });
    }
    throw new Error(`unexpected fetch ${url}`);
  });
  renderBlock();

  expect(await screen.findByText("Загружаем расписание…")).toBeInTheDocument();
  await waitFor(() =>
    expect(client.getQueryData(getListSeriesQueryKey({ child_id: "c1" }))).toBeDefined(),
  );
  expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
  release();

  expect(await screen.findAllByRole("listitem")).toHaveLength(2);
});

test("shows the settings load error instead of an endless loading state", async () => {
  settingsResponse = () =>
    jsonResponse(500, { error: { code: "boom", message: "Сбой", details: {} } });
  renderBlock();

  expect(
    await screen.findByText("Не удалось загрузить настройки репетитора. Обновите страницу."),
  ).toBeInTheDocument();
  expect(screen.queryByText("Загружаем расписание…")).not.toBeInTheDocument();
  expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
});

test("finishing asks for confirmation and then sends DELETE", async () => {
  routes["DELETE /api/admin/series/s1"] = () => new Response(null, { status: 204 });
  const user = userEvent.setup();
  renderBlock();

  await user.click(await screen.findByRole("button", { name: "Завершить расписание" }));
  const dialog = await screen.findByRole("dialog");
  expect(
    within(dialog).getByText(
      "Будущие занятия этого расписания будут удалены. Прошедшие и отмеченные останутся.",
    ),
  ).toBeInTheDocument();
  expect(calls("DELETE", "/api/admin/series/s1")).toHaveLength(0);

  await user.click(within(dialog).getByRole("button", { name: "Завершить" }));

  await waitFor(() => expect(calls("DELETE", "/api/admin/series/s1")).toHaveLength(1));
  await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Расписание завершено"));
  expect(client.invalidateQueries).toHaveBeenCalledWith({ predicate: expect.any(Function) });
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

test("cancelling the confirmation sends nothing", async () => {
  const user = userEvent.setup();
  renderBlock();

  await user.click(await screen.findByRole("button", { name: "Завершить расписание" }));
  const dialog = await screen.findByRole("dialog");
  await user.click(within(dialog).getByRole("button", { name: "Отмена" }));

  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(false);
});

test("a refused finish keeps the dialog open with the error", async () => {
  routes["DELETE /api/admin/series/s1"] = () =>
    jsonResponse(409, {
      error: { code: "series_archived", message: "Расписание уже завершено", details: {} },
    });
  const user = userEvent.setup();
  renderBlock();

  await user.click(await screen.findByRole("button", { name: "Завершить расписание" }));
  const dialog = await screen.findByRole("dialog");
  await user.click(within(dialog).getByRole("button", { name: "Завершить" }));

  expect(await within(dialog).findByText("Расписание уже завершено")).toBeInTheDocument();
  expect(toastSuccess).not.toHaveBeenCalled();
});
