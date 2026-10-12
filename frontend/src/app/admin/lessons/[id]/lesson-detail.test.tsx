import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const toastSuccess = vi.fn();
const toastWarning = vi.fn();
const push = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "l1" }),
  useRouter: () => ({ push, replace: vi.fn() }),
}));
vi.mock("sonner", () => ({
  toast: {
    success: (message: string) => toastSuccess(message),
    warning: (message: string) => toastWarning(message),
  },
}));

import type { AdminLessonDetail } from "@/api/generated/model";

import { LessonDetail } from "./lesson-detail";

// «Сейчас» заморожено (только `Date`, таймеры настоящие): PAST и FUTURE не зависят от часов машины.
const NOW = new Date("2026-10-12T09:00:00Z");
const PAST = "2026-10-06T15:00:00Z"; // вт, 18:00 по Москве
const FUTURE = "2026-10-20T15:00:00Z"; // вт, 18:00 по Москве

const DETACH_WARNING = "Занятие отделится от расписания";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function makeLesson(overrides: Partial<AdminLessonDetail> = {}): AdminLessonDetail {
  return {
    id: "l1",
    created_at: "2026-10-01T10:00:00Z",
    duration_min: 60,
    has_notes: false,
    has_requests: false,
    is_detached: false,
    join_url: "https://meet.example.com/petya",
    kind: "regular",
    meeting_url: null,
    notes: { shared_text: "", private_text: "" },
    series_id: null,
    starts_at: FUTURE,
    status: "scheduled",
    student: {
      child_id: "c1",
      lead_id: null,
      name: "Петя",
      family_id: "f1",
      family_name: "Ивановы",
    },
    ...overrides,
  };
}

let lesson: AdminLessonDetail;
let timezone: string;
let settingsResponse: () => Promise<Response>;
let patchResponse: (body: Record<string, unknown>) => Response;
let deleteResponse: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
let client: QueryClient;

function stubApi() {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (url === "/api/admin/settings") return settingsResponse();
    if (url === "/api/admin/lessons/l1" && method === "GET") return jsonResponse(200, lesson);
    if (url === "/api/admin/lessons/l1" && method === "PATCH") {
      return patchResponse(JSON.parse(init?.body as string));
    }
    if (url === "/api/admin/lessons/l1" && method === "DELETE") return deleteResponse();
    if (url === "/api/admin/lessons/l1/notes" && method === "PUT") {
      const notes = JSON.parse(init?.body as string);
      lesson = { ...lesson, notes, has_notes: true };
      return jsonResponse(200, notes);
    }
    throw new Error(`unexpected fetch ${method} ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function calls(method: string, url = "/api/admin/lessons/l1") {
  return fetchMock.mock.calls.filter(([u, init]) => u === url && (init?.method ?? "GET") === method);
}

function bodies(method: string, url?: string): unknown[] {
  return calls(method, url).map(([, init]) => JSON.parse((init as RequestInit).body as string));
}

function renderDetail() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LessonDetail />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
  toastSuccess.mockReset();
  toastWarning.mockReset();
  push.mockReset();
  timezone = "Europe/Moscow";
  lesson = makeLesson();
  settingsResponse = async () => jsonResponse(200, { timezone, cancel_policy_hours: 24 });
  patchResponse = (body) => {
    lesson = { ...lesson, ...(body as Partial<AdminLessonDetail>) };
    return jsonResponse(200, { ...lesson, warnings: [] });
  };
  deleteResponse = () => new Response(null, { status: 204 });
  document.cookie = "csrf_token=t";
  stubApi();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test("shows lesson, student link and needs-marking badge", async () => {
  lesson = makeLesson({ starts_at: PAST, series_id: "s1" });
  renderDetail();

  expect(await screen.findByRole("heading", { name: "Петя" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Петя" })).toHaveAttribute("href", "/admin/families/f1");
  expect(screen.getByText("Ивановы")).toBeInTheDocument();
  expect(screen.getByText(/вт, 6 окт\., 18:00–19:00/)).toBeInTheDocument();
  expect(screen.getByText(/60 мин/)).toBeInTheDocument();
  expect(screen.getByText("Запланировано", { selector: "[data-slot=badge]" })).toBeInTheDocument();
  expect(screen.getByText("Нужно отметить")).toBeInTheDocument();
  expect(screen.getByText("Из расписания")).toBeInTheDocument();
  expect(screen.queryByText("Перенесено")).toBeNull();
  expect(screen.getByRole("link", { name: "Подключиться" })).toHaveAttribute(
    "href",
    "https://meet.example.com/petya",
  );
});

test("a moved series lesson is marked «Перенесено»", async () => {
  lesson = makeLesson({ series_id: "s1", is_detached: true });
  renderDetail();

  expect(await screen.findByText("Перенесено")).toBeInTheDocument();
  expect(screen.queryByText("Нужно отметить")).toBeNull();
});

test("a trial lesson links to the lead", async () => {
  lesson = makeLesson({
    kind: "trial",
    student: { child_id: null, lead_id: "ld1", name: "Маша", family_id: null, family_name: null },
  });
  renderDetail();

  expect(await screen.findByRole("link", { name: "Маша" })).toHaveAttribute(
    "href",
    "/admin/leads/ld1",
  );
  expect(screen.getByText("Пробное")).toBeInTheDocument();
});

test("without a join link there is no «Подключиться»", async () => {
  lesson = makeLesson({ join_url: null });
  renderDetail();

  await screen.findByRole("heading", { name: "Петя" });
  expect(screen.queryByRole("link", { name: "Подключиться" })).toBeNull();
});

test("future lesson cannot be marked completed or no-show", async () => {
  renderDetail();

  const select = await screen.findByLabelText("Статус");
  expect(within(select).getByRole("option", { name: "Проведено" })).toBeDisabled();
  expect(within(select).getByRole("option", { name: "Пропуск" })).toBeDisabled();
  expect(within(select).getByRole("option", { name: "Отменено" })).toBeEnabled();
  expect(within(select).getByRole("option", { name: "Поздняя отмена" })).toBeEnabled();
});

test("a started lesson can be marked completed", async () => {
  lesson = makeLesson({ starts_at: PAST });
  renderDetail();

  const select = await screen.findByLabelText("Статус");
  expect(within(select).getByRole("option", { name: "Проведено" })).toBeEnabled();
  expect(within(select).getByRole("option", { name: "Пропуск" })).toBeEnabled();
});

test("status change sends PATCH and refreshes", async () => {
  const user = userEvent.setup();
  renderDetail();

  await user.selectOptions(await screen.findByLabelText("Статус"), "cancelled_late");

  await waitFor(() => expect(bodies("PATCH")).toEqual([{ status: "cancelled_late" }]));
  await waitFor(() => expect(calls("GET")).toHaveLength(2));
  expect(await screen.findByText("Засчитывается как проведённое")).toBeInTheDocument();
  expect(screen.getByLabelText("Статус")).toHaveValue("cancelled_late");
  expect(toastSuccess).toHaveBeenCalledWith("Статус обновлён");
});

test("a refused status change shows the reason", async () => {
  patchResponse = () =>
    jsonResponse(409, {
      error: { code: "lesson_not_started", message: "Занятие ещё не началось", details: {} },
    });
  lesson = makeLesson({ starts_at: PAST });
  const user = userEvent.setup();
  renderDetail();

  await user.selectOptions(await screen.findByLabelText("Статус"), "completed");

  expect(await screen.findByText("Занятие ещё не началось")).toBeInTheDocument();
  expect(screen.getByLabelText("Статус")).toHaveValue("scheduled");
  expect(toastSuccess).not.toHaveBeenCalled();
});

test("edit time of series lesson warns about detaching and sends UTC", async () => {
  lesson = makeLesson({ series_id: "s1" });
  patchResponse = (body) => {
    lesson = { ...lesson, starts_at: body.starts_at as string, is_detached: true };
    return jsonResponse(200, {
      ...lesson,
      warnings: [
        {
          code: "overlap",
          lesson_id: "l9",
          starts_at: "2026-10-20T16:30:00Z",
          message: "Пересекается с занятием Саша в 19:30",
        },
      ],
    });
  };
  const user = userEvent.setup();
  renderDetail();

  await user.click(await screen.findByRole("button", { name: "Перенести" }));
  const dialog = await screen.findByRole("dialog");
  expect(within(dialog).getByLabelText("Дата")).toHaveValue("2026-10-20");
  expect(within(dialog).getByLabelText("Время")).toHaveValue("18:00");
  expect(within(dialog).getByLabelText("Длительность, мин")).toHaveValue(60);
  // Время не менялось — предупреждения ещё нет.
  expect(within(dialog).queryByText(DETACH_WARNING)).toBeNull();

  const submit = within(dialog).getByRole("button", { name: "Сохранить" });
  await waitFor(() => expect(submit).toBeEnabled());
  fireEvent.change(within(dialog).getByLabelText("Время"), { target: { value: "19:00" } });
  expect(within(dialog).getByText(DETACH_WARNING)).toBeInTheDocument();
  await user.click(submit);

  await waitFor(() => expect(bodies("PATCH")).toEqual([{ starts_at: "2026-10-20T16:00:00.000Z" }]));
  await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Занятие обновлено"));
  expect(toastWarning).toHaveBeenCalledWith("Пересекается с занятием Саша в 19:30");
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(await screen.findByText("Перенесено")).toBeInTheDocument();
});

test("the detaching warning follows the date and time fields, live", async () => {
  lesson = makeLesson({ series_id: "s1" });
  const user = userEvent.setup();
  renderDetail();

  await user.click(await screen.findByRole("button", { name: "Перенести" }));
  const dialog = await screen.findByRole("dialog");
  expect(within(dialog).queryByText(DETACH_WARNING)).toBeNull();

  // Длительность и ссылка занятие от серии не отделяют.
  fireEvent.change(within(dialog).getByLabelText("Длительность, мин"), { target: { value: "45" } });
  await user.type(within(dialog).getByLabelText("Ссылка на занятие"), "https://meet.example.com/x");
  expect(within(dialog).queryByText(DETACH_WARNING)).toBeNull();

  fireEvent.change(within(dialog).getByLabelText("Дата"), { target: { value: "2026-10-21" } });
  expect(within(dialog).getByText(DETACH_WARNING)).toBeInTheDocument();

  // Вернули исходную дату — предупреждение пропало.
  fireEvent.change(within(dialog).getByLabelText("Дата"), { target: { value: "2026-10-20" } });
  expect(within(dialog).queryByText(DETACH_WARNING)).toBeNull();

  fireEvent.change(within(dialog).getByLabelText("Время"), { target: { value: "19:00" } });
  expect(within(dialog).getByText(DETACH_WARNING)).toBeInTheDocument();
});

test("an already detached lesson gets no detaching warning even when moved", async () => {
  lesson = makeLesson({ series_id: "s1", is_detached: true });
  const user = userEvent.setup();
  renderDetail();

  await user.click(await screen.findByRole("button", { name: "Перенести" }));
  const dialog = await screen.findByRole("dialog");
  fireEvent.change(within(dialog).getByLabelText("Время"), { target: { value: "19:00" } });
  expect(within(dialog).queryByText(DETACH_WARNING)).toBeNull();
});

test("the detaching warning is absent for a one-off lesson", async () => {
  const user = userEvent.setup();
  renderDetail();

  await user.click(await screen.findByRole("button", { name: "Перенести" }));
  const dialog = await screen.findByRole("dialog");
  expect(within(dialog).queryByText("Занятие отделится от расписания")).toBeNull();
});

test("edit sends only changed fields; an empty link clears it", async () => {
  lesson = makeLesson({ meeting_url: "https://meet.example.com/old" });
  const user = userEvent.setup();
  renderDetail();

  await user.click(await screen.findByRole("button", { name: "Перенести" }));
  const dialog = await screen.findByRole("dialog");
  const submit = within(dialog).getByRole("button", { name: "Сохранить" });
  await waitFor(() => expect(submit).toBeEnabled());
  fireEvent.change(within(dialog).getByLabelText("Длительность, мин"), { target: { value: "45" } });
  await user.clear(within(dialog).getByLabelText("Ссылка на занятие"));
  await user.click(submit);

  await waitFor(() => expect(bodies("PATCH")).toEqual([{ duration_min: 45, meeting_url: null }]));
});

test("edit submit is disabled until the tutor time zone is loaded", async () => {
  let release: () => void = () => undefined;
  settingsResponse = () =>
    new Promise((resolve) => {
      release = () => resolve(jsonResponse(200, { timezone: "Asia/Yekaterinburg", cancel_policy_hours: 24 }));
    });
  const user = userEvent.setup();
  renderDetail();

  await user.click(await screen.findByRole("button", { name: "Перенести" }));
  const dialog = await screen.findByRole("dialog");
  expect(within(dialog).getByRole("button", { name: "Сохранить" })).toBeDisabled();

  release();
  await waitFor(() => expect(within(dialog).getByRole("button", { name: "Сохранить" })).toBeEnabled());
  // Времена пересчитаны в загруженном поясе: 15:00Z = 20:00 по Екатеринбургу.
  expect(within(dialog).getByLabelText("Время")).toHaveValue("20:00");
});

test("the edit dialog shows the settings load error instead of an endless disabled form", async () => {
  settingsResponse = async () =>
    jsonResponse(500, { error: { code: "boom", message: "Сбой", details: {} } });
  const user = userEvent.setup();
  renderDetail();

  await user.click(await screen.findByRole("button", { name: "Перенести" }));
  const dialog = await screen.findByRole("dialog");

  expect(
    await within(dialog).findByText("Не удалось загрузить настройки репетитора. Обновите страницу."),
  ).toBeInTheDocument();
  expect(within(dialog).queryByRole("button", { name: "Сохранить" })).not.toBeInTheDocument();
});

test("a conflict while rescheduling is shown in the dialog", async () => {
  patchResponse = () =>
    jsonResponse(409, {
      error: { code: "lesson_slot_taken", message: "В это время уже есть занятие", details: {} },
    });
  const user = userEvent.setup();
  renderDetail();

  await user.click(await screen.findByRole("button", { name: "Перенести" }));
  const dialog = await screen.findByRole("dialog");
  const submit = within(dialog).getByRole("button", { name: "Сохранить" });
  await waitFor(() => expect(submit).toBeEnabled());
  fireEvent.change(within(dialog).getByLabelText("Время"), { target: { value: "19:00" } });
  await user.click(submit);

  expect(await within(dialog).findByText("В это время уже есть занятие")).toBeInTheDocument();
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(toastSuccess).not.toHaveBeenCalled();
});

test("only a scheduled lesson can be rescheduled", async () => {
  lesson = makeLesson({ status: "completed", starts_at: PAST });
  renderDetail();

  await screen.findByRole("heading", { name: "Петя" });
  expect(screen.queryByRole("button", { name: "Перенести" })).toBeNull();
});

test("delete only for future scheduled", async () => {
  lesson = makeLesson({ starts_at: PAST });
  const { unmount } = renderDetail();
  await screen.findByRole("heading", { name: "Петя" });
  expect(screen.queryByRole("button", { name: "Удалить" })).toBeNull();
  unmount();

  lesson = makeLesson({ status: "cancelled" });
  const second = renderDetail();
  await screen.findByRole("heading", { name: "Петя" });
  expect(screen.queryByRole("button", { name: "Удалить" })).toBeNull();
  second.unmount();

  lesson = makeLesson();
  renderDetail();
  expect(await screen.findByRole("button", { name: "Удалить" })).toBeInTheDocument();
});

test("lesson with requests hides delete and links to queue", async () => {
  lesson = makeLesson({ has_requests: true });
  renderDetail();

  expect(await screen.findByText("По занятию есть запрос семьи")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Открыть запросы" })).toHaveAttribute(
    "href",
    "/admin/requests?tab=all",
  );
  expect(screen.queryByRole("button", { name: "Удалить" })).toBeNull();
  // перенос остаётся доступным
  expect(screen.getByRole("button", { name: "Перенести" })).toBeInTheDocument();
});

test("lesson without requests has no hint", async () => {
  renderDetail();
  expect(await screen.findByRole("button", { name: "Удалить" })).toBeInTheDocument();
  expect(screen.queryByText("По занятию есть запрос семьи")).toBeNull();
});

test("confirmed delete sends DELETE, goes to the calendar and toasts", async () => {
  const user = userEvent.setup();
  renderDetail();

  await user.click(await screen.findByRole("button", { name: "Удалить" }));
  const dialog = await screen.findByRole("dialog");
  expect(calls("DELETE")).toHaveLength(0);
  await user.click(within(dialog).getByRole("button", { name: "Удалить" }));

  await waitFor(() => expect(calls("DELETE")).toHaveLength(1));
  await waitFor(() => expect(push).toHaveBeenCalledWith("/admin/calendar"));
  expect(toastSuccess).toHaveBeenCalledWith("Занятие удалено");
  expect(calls("GET")).toHaveLength(1);
});

test("a refused delete stays in the dialog", async () => {
  deleteResponse = () =>
    jsonResponse(409, {
      error: { code: "lesson_not_deletable", message: "Занятие нельзя удалить", details: {} },
    });
  const user = userEvent.setup();
  renderDetail();

  await user.click(await screen.findByRole("button", { name: "Удалить" }));
  const dialog = await screen.findByRole("dialog");
  await user.click(within(dialog).getByRole("button", { name: "Удалить" }));

  expect(await within(dialog).findByText("Занятие нельзя удалить")).toBeInTheDocument();
  expect(push).not.toHaveBeenCalled();
});

test("saves both notes", async () => {
  lesson = makeLesson({ notes: { shared_text: "старое", private_text: "" } });
  const user = userEvent.setup();
  renderDetail();

  const save = await screen.findByRole("button", { name: "Сохранить заметку" });
  expect(save).toBeDisabled();
  const shared = screen.getByLabelText("Общая — видна семье");
  const priv = screen.getByLabelText("Приватная — только для вас");
  expect(shared).toHaveValue("старое");

  await user.clear(shared);
  await user.type(shared, "Повторить Past Simple");
  await user.type(priv, "Слабое аудирование");
  expect(save).toBeEnabled();
  await user.click(save);

  await waitFor(() =>
    expect(bodies("PUT", "/api/admin/lessons/l1/notes")).toEqual([
      { shared_text: "Повторить Past Simple", private_text: "Слабое аудирование" },
    ]),
  );
  await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Заметка сохранена"));
  await waitFor(() => expect(screen.getByRole("button", { name: "Сохранить заметку" })).toBeDisabled());
  expect(screen.getByLabelText("Общая — видна семье")).toHaveValue("Повторить Past Simple");
});

test("leaving with unsaved notes triggers beforeunload; saved notes do not", async () => {
  const user = userEvent.setup();
  renderDetail();

  const shared = await screen.findByLabelText("Общая — видна семье");
  const clean = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(clean);
  expect(clean.defaultPrevented).toBe(false);

  await user.type(shared, "черновик");
  const dirty = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(dirty);
  expect(dirty.defaultPrevented).toBe(true);

  await user.click(screen.getByRole("button", { name: "Сохранить заметку" }));
  await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Заметка сохранена"));
  const saved = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(saved);
  expect(saved.defaultPrevented).toBe(false);
});

test("a status change does not wipe unsaved notes", async () => {
  const user = userEvent.setup();
  renderDetail();

  const shared = await screen.findByLabelText("Общая — видна семье");
  await user.type(shared, "черновик");
  await user.selectOptions(screen.getByLabelText("Статус"), "cancelled");
  await waitFor(() => expect(calls("GET")).toHaveLength(2));

  expect(screen.getByLabelText("Общая — видна семье")).toHaveValue("черновик");
});

test("a load failure shows the error and a way back", async () => {
  fetchMock.mockImplementation(async (url: string) => {
    if (url === "/api/admin/lessons/l1") {
      return jsonResponse(404, { error: { code: "not_found", message: "Занятие не найдено", details: {} } });
    }
    return jsonResponse(200, { timezone, cancel_policy_hours: 24 });
  });
  renderDetail();

  expect(await screen.findByText("Занятие не найдено")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "К календарю" })).toHaveAttribute("href", "/admin/calendar");
});
