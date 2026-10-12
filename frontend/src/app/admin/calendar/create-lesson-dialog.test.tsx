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

import { CreateLessonDialog } from "./create-lesson-dialog";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const FAMILIES = [
  {
    id: "f1",
    name: "Ивановы",
    archived_at: null,
    parent_names: ["Мария"],
    children: [
      { id: "c1", full_name: "Петя" },
      { id: "c2", full_name: "Маша" },
    ],
  },
  {
    id: "f2",
    name: "Орловы",
    archived_at: null,
    parent_names: ["Ольга"],
    children: [{ id: "c3", full_name: "Саша" }],
  },
];

const STUDENT = {
  child_id: "c1",
  lead_id: null,
  name: "Петя",
  family_id: "f1",
  family_name: "Ивановы",
};

function lessonSaved(warnings: unknown[] = []) {
  return {
    id: "l1",
    created_at: "2026-10-12T10:00:00Z",
    duration_min: 60,
    has_notes: false,
    is_detached: false,
    join_url: null,
    kind: "regular",
    meeting_url: null,
    notes: { shared_text: "", private_text: "" },
    series_id: null,
    starts_at: "2026-10-20T15:00:00Z",
    status: "scheduled",
    student: STUDENT,
    warnings,
  };
}

let timezone = "Europe/Moscow";
let settingsFail = false;
let fetchMock: ReturnType<typeof vi.fn>;
let lessonResponse: () => Response;
let client: QueryClient;
const onOpenChange = vi.fn();

function stubApi() {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/admin/settings") {
      if (settingsFail) {
        return jsonResponse(500, { error: { code: "boom", message: "Сбой", details: {} } });
      }
      return jsonResponse(200, { timezone, cancel_policy_hours: 24 });
    }
    if (url.startsWith("/api/admin/families") && init?.method === "GET") {
      return jsonResponse(200, FAMILIES);
    }
    if (url === "/api/admin/lessons" && init?.method === "POST") return lessonResponse();
    if (url === "/api/admin/series" && init?.method === "POST") {
      return jsonResponse(201, {
        lessons_created: 8,
        lessons_updated: 0,
        lessons_removed: 0,
        warnings: [],
        series: {
          id: "s1",
          child_id: "c1",
          child_name: "Петя",
          rrule: "FREQ=WEEKLY;BYDAY=TU",
          local_start_time: "18:00:00",
          duration_min: 60,
          meeting_url: null,
          starts_on: "2026-10-20",
          ends_on: null,
          archived_at: null,
        },
      });
    }
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function posts(url: string): unknown[] {
  return fetchMock.mock.calls
    .filter(([u, init]) => u === url && init?.method === "POST")
    .map(([, init]) => JSON.parse((init as RequestInit).body as string));
}

function renderDialogNow(initial = { date: "2026-10-20", time: "18:00" }) {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.spyOn(client, "invalidateQueries");
  return render(
    <QueryClientProvider client={client}>
      <CreateLessonDialog open onOpenChange={onOpenChange} initial={initial} />
    </QueryClientProvider>,
  );
}

/** Рендерит диалог и ждёт пояс репетитора: до этого отправка заблокирована. */
async function renderDialog(initial = { date: "2026-10-20", time: "18:00" }) {
  const view = renderDialogNow(initial);
  await waitFor(() => expect(screen.getByRole("button", { name: "Создать" })).toBeEnabled());
  return view;
}

beforeEach(() => {
  toastSuccess.mockReset();
  toastWarning.mockReset();
  onOpenChange.mockReset();
  timezone = "Europe/Moscow";
  settingsFail = false;
  lessonResponse = () => jsonResponse(201, lessonSaved());
  document.cookie = "csrf_token=t";
  stubApi();
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

async function chooseStudent(user: ReturnType<typeof userEvent.setup>, childId: string) {
  const select = await screen.findByLabelText("Ученик");
  await waitFor(() => expect(select.querySelectorAll("option").length).toBeGreaterThan(1));
  await user.selectOptions(select, childId);
}

test("lists active children as «Семья — ребёнок»", async () => {
  await renderDialog();
  const select = await screen.findByLabelText("Ученик");
  await waitFor(() => expect(select.querySelectorAll("option")).toHaveLength(4));
  expect(
    Array.from(select.querySelectorAll("option")).map((option) => option.textContent),
  ).toEqual(["Выберите ученика", "Ивановы — Петя", "Ивановы — Маша", "Орловы — Саша"]);
});

test("prefills the date and time of the clicked slot", async () => {
  await renderDialog({ date: "2026-10-20", time: "20:00" });
  expect(await screen.findByLabelText("Дата")).toHaveValue("2026-10-20");
  expect(screen.getByLabelText("Время")).toHaveValue("20:00");
  expect(screen.getByLabelText("Длительность, мин")).toHaveValue(60);
});

test("one-off lesson converts tutor-zone time to UTC", async () => {
  const user = userEvent.setup();
  await renderDialog({ date: "2026-10-19", time: "10:00" });

  await chooseStudent(user, "c1");
  fireEvent.change(screen.getByLabelText("Дата"), { target: { value: "2026-10-20" } });
  fireEvent.change(screen.getByLabelText("Время"), { target: { value: "18:00" } });
  await user.click(screen.getByRole("button", { name: "Создать" }));

  await waitFor(() => expect(posts("/api/admin/lessons")).toHaveLength(1));
  expect(posts("/api/admin/lessons")[0]).toEqual({
    child_id: "c1",
    starts_at: "2026-10-20T15:00:00.000Z",
    duration_min: 60,
  });
  await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Занятие создано"));
  expect(client.invalidateQueries).toHaveBeenCalledWith({ predicate: expect.any(Function) });
  expect(onOpenChange).toHaveBeenCalledWith(false);
});

test("uses the tutor zone, not the browser zone", async () => {
  timezone = "Asia/Yekaterinburg";
  const user = userEvent.setup();
  await renderDialog({ date: "2026-10-20", time: "20:00" });

  await chooseStudent(user, "c3");
  // The zone settings arrive asynchronously; wait for them before submitting.
  await waitFor(() => expect(client.getQueryData(["/api/admin/settings"])).toBeDefined());
  await user.type(screen.getByLabelText("Ссылка на занятие"), "https://meet.example.com/a");
  await user.click(screen.getByRole("button", { name: "Создать" }));

  await waitFor(() => expect(posts("/api/admin/lessons")).toHaveLength(1));
  expect(posts("/api/admin/lessons")[0]).toEqual({
    child_id: "c3",
    starts_at: "2026-10-20T15:00:00.000Z",
    duration_min: 60,
    meeting_url: "https://meet.example.com/a",
  });
});

test("requires a student", async () => {
  const user = userEvent.setup();
  await renderDialog();

  await user.click(await screen.findByRole("button", { name: "Создать" }));

  expect(await screen.findByText("Выберите ученика", { selector: "p" })).toBeInTheDocument();
  expect(posts("/api/admin/lessons")).toHaveLength(0);
});

test("validates the duration range", async () => {
  const user = userEvent.setup();
  await renderDialog();

  await chooseStudent(user, "c1");
  fireEvent.change(screen.getByLabelText("Длительность, мин"), { target: { value: "10" } });
  await user.click(screen.getByRole("button", { name: "Создать" }));

  expect(await screen.findByText("Не менее 15 минут")).toBeInTheDocument();
  expect(posts("/api/admin/lessons")).toHaveLength(0);
});

test("overlap warnings become toasts", async () => {
  lessonResponse = () =>
    jsonResponse(
      201,
      lessonSaved([
        {
          code: "overlap",
          lesson_id: "l9",
          starts_at: "2026-10-20T15:30:00Z",
          message: "Пересекается с занятием Саша в 18:30",
        },
      ]),
    );
  const user = userEvent.setup();
  await renderDialog();

  await chooseStudent(user, "c1");
  await user.click(screen.getByRole("button", { name: "Создать" }));

  await waitFor(() =>
    expect(toastWarning).toHaveBeenCalledWith("Пересекается с занятием Саша в 18:30"),
  );
  expect(toastSuccess).toHaveBeenCalledWith("Занятие создано");
});

test("a conflict is shown in the form and the dialog stays open", async () => {
  lessonResponse = () =>
    jsonResponse(409, { error: { code: "child_archived", message: "Ученик в архиве", details: {} } });
  const user = userEvent.setup();
  await renderDialog();

  await chooseStudent(user, "c1");
  await user.click(screen.getByRole("button", { name: "Создать" }));

  expect(await screen.findByText("Ученик в архиве")).toBeInTheDocument();
  expect(onOpenChange).not.toHaveBeenCalled();
  expect(toastSuccess).not.toHaveBeenCalled();
});

test("the regular tab creates a series for the chosen student with the slot prefilled", async () => {
  const user = userEvent.setup();
  await renderDialog({ date: "2026-10-20", time: "18:00" });

  await chooseStudent(user, "c1");
  await user.click(screen.getByRole("button", { name: "Регулярное" }));
  expect(screen.getByRole("checkbox", { name: "вт" })).toBeChecked();
  expect(screen.getByLabelText("Время")).toHaveValue("18:00");
  await user.click(screen.getByRole("button", { name: "Создать" }));

  await waitFor(() => expect(posts("/api/admin/series")).toHaveLength(1));
  expect(posts("/api/admin/series")[0]).toEqual({
    child_id: "c1",
    rrule: "FREQ=WEEKLY;BYDAY=TU",
    local_start_time: "18:00",
    duration_min: 60,
    starts_on: "2026-10-20",
  });
  await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Расписание создано: 8 занятий"));
  expect(posts("/api/admin/lessons")).toHaveLength(0);
});

test("the one-off submit is disabled until the tutor time zone is loaded", async () => {
  settingsFail = true;
  const user = userEvent.setup();
  renderDialogNow();

  await chooseStudent(user, "c1");
  await waitFor(() =>
    expect(fetchMock.mock.calls.some(([url]) => url === "/api/admin/settings")).toBe(true),
  );
  const submit = screen.getByRole("button", { name: "Создать" });
  expect(submit).toBeDisabled();
  await user.click(submit);
  expect(posts("/api/admin/lessons")).toHaveLength(0);
});

test("the regular submit is disabled until the tutor time zone is loaded", async () => {
  settingsFail = true;
  const user = userEvent.setup();
  renderDialogNow();

  await chooseStudent(user, "c1");
  await user.click(screen.getByRole("button", { name: "Регулярное" }));
  await waitFor(() =>
    expect(fetchMock.mock.calls.some(([url]) => url === "/api/admin/settings")).toBe(true),
  );
  const submit = screen.getByRole("button", { name: "Создать" });
  expect(submit).toBeDisabled();
  await user.click(submit);
  expect(posts("/api/admin/series")).toHaveLength(0);
});

test("the regular tab also requires a student", async () => {
  const user = userEvent.setup();
  await renderDialog();

  await user.click(await screen.findByRole("button", { name: "Регулярное" }));
  await user.click(screen.getByRole("button", { name: "Создать" }));

  expect(await screen.findByText("Выберите ученика", { selector: "p" })).toBeInTheDocument();
  expect(posts("/api/admin/series")).toHaveLength(0);
});
