import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const toastSuccess = vi.fn();
const toastError = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "f1" }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock("sonner", () => ({
  toast: {
    success: (message: string) => toastSuccess(message),
    error: (message: string) => toastError(message),
  },
}));

import { FamilyDetail } from "./family-detail";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function errorResponse(status: number, code: string, message: string, details = {}): Response {
  return jsonResponse(status, { error: { code, message, details } });
}

const parent = {
  user_id: "u2",
  full_name: "Мария Иванова",
  phone: "+7 900 000-00-00",
  email: "maria@example.com",
  is_active: true,
  last_login_at: "2026-10-01T09:30:00Z",
};

const child = {
  id: "c1",
  full_name: "Петя",
  birth_year: 2015,
  english_level: "A2",
  default_meeting_url: "https://meet.example.com/petya",
  archived_at: null as string | null,
  account: null as null | { user_id: string; username: string; is_active: boolean },
};

type Family = {
  id: string;
  name: string;
  tutor_comment: string | null;
  archived_at: string | null;
  created_at: string;
  parents: (typeof parent)[];
  children: (typeof child)[];
  pending_invitation: null | { created_at: string; expires_at: string };
};

let family: Family;
let seriesList: unknown[];
let routes: Record<string, (body: unknown) => Response>;
let fetchMock: ReturnType<typeof vi.fn>;

function stubApi() {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url}`;
    if (key === "GET /api/admin/families/f1") return jsonResponse(200, family);
    if (key === "GET /api/admin/series?child_id=c1") return jsonResponse(200, seriesList);
    if (key === "GET /api/admin/settings") {
      return jsonResponse(200, { timezone: "Europe/Moscow", cancel_policy_hours: 24 });
    }
    const handler = routes[key];
    if (!handler) throw new Error(`unexpected fetch ${key}`);
    return handler(init?.body ? JSON.parse(String(init.body)) : undefined);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function calls(method: string, url: string) {
  return fetchMock.mock.calls.filter(([u, init]) => u === url && init?.method === method);
}

function bodyOf(call: unknown[] | undefined): unknown {
  return JSON.parse(String((call?.[1] as RequestInit | undefined)?.body));
}

function renderDetail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <FamilyDetail />
    </QueryClientProvider>,
  );
}

function sectionOf(heading: string): HTMLElement {
  return screen.getByRole("heading", { name: heading }).closest("section") as HTMLElement;
}

beforeEach(() => {
  toastSuccess.mockReset();
  toastError.mockReset();
  document.cookie = "csrf_token=t";
  family = {
    id: "f1",
    name: "Семья Ивановых",
    tutor_comment: "Пишут вечером",
    archived_at: null,
    created_at: "2026-09-01T10:00:00Z",
    parents: [parent],
    children: [{ ...child }],
    pending_invitation: null,
  };
  routes = {};
  seriesList = [];
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test("показывает семью, родителя и ребёнка", async () => {
  stubApi();
  renderDetail();
  expect(await screen.findByRole("heading", { name: "Семья Ивановых" })).toBeInTheDocument();
  expect(screen.getByText("Пишут вечером")).toBeInTheDocument();
  const parents = sectionOf("Родители");
  expect(within(parents).getByText("Мария Иванова")).toBeInTheDocument();
  expect(within(parents).getByText("01.10.2026 12:30")).toBeInTheDocument();
  expect(within(parents).getByText("Активен")).toBeInTheDocument();
  const children = sectionOf("Дети");
  expect(within(children).getByText("Петя")).toBeInTheDocument();
  expect(within(children).getByText(/2015/)).toBeInTheDocument();
  expect(within(children).getByText(/A2/)).toBeInTheDocument();
  expect(within(children).getByText("https://meet.example.com/petya")).toBeInTheDocument();
  expect(within(children).getByText("Логин не выдан")).toBeInTheDocument();
});

test("подсказка про приглашение, если родителей нет", async () => {
  family.parents = [];
  stubApi();
  renderDetail();
  expect(
    await screen.findByText("Создайте ссылку-приглашение и отправьте её родителю"),
  ).toBeInTheDocument();
});

test("подсказки нет, если есть родитель или активное приглашение", async () => {
  stubApi();
  const { unmount } = renderDetail();
  await screen.findByRole("heading", { name: "Семья Ивановых" });
  expect(screen.queryByText(/Создайте ссылку-приглашение и отправьте/)).not.toBeInTheDocument();
  unmount();

  family.parents = [];
  family.pending_invitation = { created_at: "2026-10-10T10:00:00Z", expires_at: "2026-10-12T09:00:00Z" };
  renderDetail();
  await screen.findByText(/Ссылка отправлена/);
  expect(screen.queryByText(/Создайте ссылку-приглашение и отправьте/)).not.toBeInTheDocument();
});

test("действующее приглашение: срок и предупреждение", async () => {
  family.pending_invitation = { created_at: "2026-10-10T10:00:00Z", expires_at: "2026-10-12T09:00:00Z" };
  stubApi();
  renderDetail();
  expect(
    await screen.findByText("Ссылка отправлена, действует до 12.10.2026 12:00"),
  ).toBeInTheDocument();
  expect(screen.getByText(/Новая ссылка отменит прежнюю/)).toBeInTheDocument();
});

test("создание приглашения показывает ссылку для копирования", async () => {
  routes["POST /api/admin/families/f1/invitations"] = () =>
    jsonResponse(201, { url: "https://app.example.com/invite/abc", expires_at: "2026-10-12T09:00:00Z" });
  stubApi();
  renderDetail();
  await screen.findByRole("heading", { name: "Семья Ивановых" });
  const section = sectionOf("Приглашение");

  await userEvent.type(within(section).getByLabelText("ФИО"), "Анна Петрова");
  await userEvent.click(within(section).getByRole("button", { name: "Создать ссылку-приглашение" }));

  const link = await within(section).findByDisplayValue("https://app.example.com/invite/abc");
  expect(link).toHaveAttribute("readonly");
  expect(within(section).getByText("Действует до 12.10.2026 12:00")).toBeInTheDocument();
  expect(bodyOf(calls("POST", "/api/admin/families/f1/invitations")[0])).toEqual({
    prefill_full_name: "Анна Петрова",
    prefill_phone: null,
  });
  expect(toastSuccess).toHaveBeenCalledWith("Ссылка-приглашение создана");
});

test("архивация требует подтверждения", async () => {
  routes["PATCH /api/admin/families/f1"] = (body) => {
    family = { ...family, archived_at: "2026-10-11T10:00:00Z" };
    return jsonResponse(200, { ...family, requested: body });
  };
  stubApi();
  renderDetail();
  await userEvent.click(await screen.findByRole("button", { name: "В архив" }));

  const dialog = await screen.findByRole("dialog");
  expect(calls("PATCH", "/api/admin/families/f1")).toHaveLength(0);
  await userEvent.click(within(dialog).getByRole("button", { name: "Да, в архив" }));

  await waitFor(() => expect(calls("PATCH", "/api/admin/families/f1")).toHaveLength(1));
  expect(bodyOf(calls("PATCH", "/api/admin/families/f1")[0])).toEqual({ archived: true });
  expect(await screen.findByText("В архиве")).toBeInTheDocument();
  expect(await screen.findByRole("button", { name: "Вернуть из архива" })).toBeInTheDocument();
  expect(toastSuccess).toHaveBeenCalledWith("Семья отправлена в архив");
});

test("отмена подтверждения ничего не отправляет", async () => {
  stubApi();
  renderDetail();
  await userEvent.click(await screen.findByRole("button", { name: "В архив" }));
  const dialog = await screen.findByRole("dialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Отмена" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(calls("PATCH", "/api/admin/families/f1")).toHaveLength(0);
});

test("возврат семьи из архива", async () => {
  family.archived_at = "2026-10-01T10:00:00Z";
  routes["PATCH /api/admin/families/f1"] = () => {
    family = { ...family, archived_at: null };
    return jsonResponse(200, family);
  };
  stubApi();
  renderDetail();
  expect(await screen.findByText("В архиве")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Вернуть из архива" }));
  const dialog = await screen.findByRole("dialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Да, вернуть" }));

  await waitFor(() =>
    expect(bodyOf(calls("PATCH", "/api/admin/families/f1")[0])).toEqual({ archived: false }),
  );
  await waitFor(() => expect(screen.queryByText("В архиве")).not.toBeInTheDocument());
});

test("редактирование названия и комментария", async () => {
  routes["PATCH /api/admin/families/f1"] = (body) => {
    family = { ...family, ...(body as object) } as Family;
    return jsonResponse(200, family);
  };
  stubApi();
  renderDetail();
  await userEvent.click(await screen.findByRole("button", { name: "Изменить семью" }));
  const dialog = await screen.findByRole("dialog");
  const name = within(dialog).getByLabelText("Название");
  expect(name).toHaveValue("Семья Ивановых");
  await userEvent.clear(name);
  await userEvent.type(name, "Семья Иванов-Петровых");
  await userEvent.clear(within(dialog).getByLabelText("Комментарий"));
  await userEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

  await waitFor(() =>
    expect(bodyOf(calls("PATCH", "/api/admin/families/f1")[0])).toEqual({
      name: "Семья Иванов-Петровых",
      tutor_comment: null,
    }),
  );
  expect(await screen.findByRole("heading", { name: "Семья Иванов-Петровых" })).toBeInTheDocument();
  expect(toastSuccess).toHaveBeenCalledWith("Семья сохранена");
});

test("блокировка родителя требует подтверждения", async () => {
  routes["PATCH /api/admin/users/u2"] = () => {
    family = { ...family, parents: [{ ...parent, is_active: false }] };
    return new Response(null, { status: 204 });
  };
  stubApi();
  renderDetail();
  await userEvent.click(await screen.findByRole("button", { name: "Заблокировать" }));
  const dialog = await screen.findByRole("dialog");
  expect(calls("PATCH", "/api/admin/users/u2")).toHaveLength(0);
  await userEvent.click(within(dialog).getByRole("button", { name: "Да, заблокировать" }));

  await waitFor(() =>
    expect(bodyOf(calls("PATCH", "/api/admin/users/u2")[0])).toEqual({ is_active: false }),
  );
  expect(await screen.findByText("Заблокирован")).toBeInTheDocument();
  expect(await screen.findByRole("button", { name: "Разблокировать" })).toBeInTheDocument();
});

test("разблокировка родителя без подтверждения", async () => {
  family.parents = [{ ...parent, is_active: false }];
  routes["PATCH /api/admin/users/u2"] = () => new Response(null, { status: 204 });
  stubApi();
  renderDetail();
  await userEvent.click(await screen.findByRole("button", { name: "Разблокировать" }));
  await waitFor(() =>
    expect(bodyOf(calls("PATCH", "/api/admin/users/u2")[0])).toEqual({ is_active: true }),
  );
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("ссылка для смены пароля родителя открывается в диалоге", async () => {
  routes["POST /api/admin/users/u2/reset-link"] = () =>
    jsonResponse(200, { url: "https://app.example.com/reset/xyz", expires_at: "2026-10-12T09:00:00Z" });
  stubApi();
  renderDetail();
  const row = (await screen.findByText("Мария Иванова")).closest("tr") as HTMLElement;
  await userEvent.click(within(row).getByRole("button", { name: "Ссылка для смены пароля" }));

  const dialog = await screen.findByRole("dialog");
  expect(await within(dialog).findByDisplayValue("https://app.example.com/reset/xyz")).toBeInTheDocument();
});

test("ошибка username_taken в диалоге логина ребёнка", async () => {
  routes["POST /api/admin/children/c1/account"] = () =>
    errorResponse(409, "username_taken", "Этот логин уже занят", { field: "username" });
  stubApi();
  renderDetail();
  await userEvent.click(await screen.findByRole("button", { name: "Логин и пароль" }));
  const dialog = await screen.findByRole("dialog");
  await userEvent.type(within(dialog).getByLabelText("Логин"), "petya");
  await userEvent.type(within(dialog).getByLabelText("Пароль"), "secret1");
  await userEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

  expect(await within(dialog).findByText("Этот логин уже занят")).toBeInTheDocument();
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(toastSuccess).not.toHaveBeenCalled();
});

test("ошибка политики пароля показывается под полем пароля", async () => {
  routes["POST /api/admin/children/c1/account"] = () =>
    errorResponse(422, "password_too_common", "Пароль слишком простой");
  stubApi();
  renderDetail();
  await userEvent.click(await screen.findByRole("button", { name: "Логин и пароль" }));
  const dialog = await screen.findByRole("dialog");
  await userEvent.type(within(dialog).getByLabelText("Логин"), "petya");
  await userEvent.type(within(dialog).getByLabelText("Пароль"), "qwerty");
  await userEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));
  expect(await within(dialog).findByText("Пароль слишком простой")).toBeInTheDocument();
});

test("логин ребёнка сохраняется, диалог закрывается", async () => {
  routes["POST /api/admin/children/c1/account"] = (body) => {
    const { username } = body as { username: string };
    family = {
      ...family,
      children: [{ ...child, account: { user_id: "u3", username, is_active: true } }],
    };
    return jsonResponse(200, family.children[0]);
  };
  stubApi();
  renderDetail();
  await userEvent.click(await screen.findByRole("button", { name: "Логин и пароль" }));
  const dialog = await screen.findByRole("dialog");
  await userEvent.type(within(dialog).getByLabelText("Логин"), "  petya ");
  await userEvent.type(within(dialog).getByLabelText("Пароль"), "secret1");
  await userEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

  await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Логин сохранён"));
  expect(bodyOf(calls("POST", "/api/admin/children/c1/account")[0])).toEqual({
    username: "petya",
    password: "secret1",
  });
  expect(await screen.findByText("Логин: petya")).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  // Теперь у ребёнка есть учётка — доступна ссылка для смены пароля.
  const card = screen.getByText("Петя").closest("[data-slot=card]") as HTMLElement;
  expect(within(card).getByRole("button", { name: "Ссылка для смены пароля" })).toBeInTheDocument();
});

test("добавление ребёнка с уровнем", async () => {
  routes["POST /api/admin/families/f1/children"] = () => jsonResponse(201, child);
  stubApi();
  renderDetail();
  await userEvent.click(await screen.findByRole("button", { name: "Добавить ребёнка" }));
  const dialog = await screen.findByRole("dialog");
  await userEvent.type(within(dialog).getByLabelText("Имя"), "Соня");
  await userEvent.type(within(dialog).getByLabelText("Год рождения"), "2017");
  await userEvent.click(within(dialog).getByRole("combobox", { name: "Уровень английского" }));
  await userEvent.click(await screen.findByRole("option", { name: "B1" }));
  await userEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

  await waitFor(() => expect(calls("POST", "/api/admin/families/f1/children")).toHaveLength(1));
  expect(bodyOf(calls("POST", "/api/admin/families/f1/children")[0])).toEqual({
    full_name: "Соня",
    birth_year: 2017,
    english_level: "B1",
    default_meeting_url: null,
  });
  expect(toastSuccess).toHaveBeenCalledWith("Ребёнок добавлен");
});

test("ошибка валидации года рождения под полем", async () => {
  routes["PATCH /api/admin/children/c1"] = () =>
    errorResponse(422, "validation_error", "Проверьте данные", {
      fields: [{ loc: ["body", "birth_year"], message: "Год рождения: от 1990 до 2026" }],
    });
  stubApi();
  renderDetail();
  await userEvent.click(await screen.findByRole("button", { name: "Изменить" }));
  const dialog = await screen.findByRole("dialog");
  expect(within(dialog).getByLabelText("Имя")).toHaveValue("Петя");
  expect(within(dialog).getByLabelText("Год рождения")).toHaveValue("2015");
  await userEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));
  expect(await within(dialog).findByText("Год рождения: от 1990 до 2026")).toBeInTheDocument();
});

test("archive confirmation mentions series", async () => {
  stubApi();
  renderDetail();
  await userEvent.click(await screen.findByRole("button", { name: "В архив ребёнка" }));
  const childDialog = await screen.findByRole("dialog");
  expect(
    within(childDialog).getByText(/Регулярные занятия будут завершены, будущие занятия удалены/),
  ).toBeInTheDocument();
  expect(calls("PATCH", "/api/admin/children/c1")).toHaveLength(0);
  await userEvent.click(within(childDialog).getByRole("button", { name: "Отмена" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

  await userEvent.click(screen.getByRole("button", { name: "В архив" }));
  const familyDialog = await screen.findByRole("dialog");
  expect(
    within(familyDialog).getByText(/Регулярные занятия будут завершены, будущие занятия удалены/),
  ).toBeInTheDocument();
});

test("архивация и возврат ребёнка", async () => {
  routes["PATCH /api/admin/children/c1"] = (body) => {
    const { archived } = body as { archived: boolean };
    family = {
      ...family,
      children: [{ ...child, archived_at: archived ? "2026-10-11T10:00:00Z" : null }],
    };
    return jsonResponse(200, family.children[0]);
  };
  stubApi();
  renderDetail();
  await userEvent.click(await screen.findByRole("button", { name: "В архив ребёнка" }));
  await userEvent.click(
    within(await screen.findByRole("dialog")).getByRole("button", { name: "Да, в архив" }),
  );
  await waitFor(() =>
    expect(bodyOf(calls("PATCH", "/api/admin/children/c1")[0])).toEqual({ archived: true }),
  );
  await userEvent.click(await screen.findByRole("button", { name: "Вернуть ребёнка" }));
  await waitFor(() =>
    expect(bodyOf(calls("PATCH", "/api/admin/children/c1")[1])).toEqual({ archived: false }),
  );
});

test("у активного ребёнка есть блок расписания с сериями", async () => {
  seriesList = [
    {
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
  ];
  stubApi();
  renderDetail();
  await screen.findByRole("heading", { name: "Семья Ивановых" });
  const children = sectionOf("Дети");
  expect(await within(children).findByText("по вт и пт в 18:00, 60 мин")).toBeInTheDocument();
  expect(within(children).getByRole("heading", { name: "Расписание" })).toBeInTheDocument();
  expect(calls("GET", "/api/admin/series?child_id=c1")).toHaveLength(1);
});

test("у ребёнка в архиве блока расписания нет, серии не запрашиваются", async () => {
  family.children = [{ ...child, archived_at: "2026-10-01T10:00:00Z" }];
  stubApi();
  renderDetail();
  await screen.findByRole("button", { name: "Вернуть ребёнка" });
  expect(screen.queryByRole("heading", { name: "Расписание" })).not.toBeInTheDocument();
  expect(calls("GET", "/api/admin/series?child_id=c1")).toHaveLength(0);
});

test("несуществующая семья", async () => {
  fetchMock = vi.fn(async () => errorResponse(404, "family_not_found", "Семья не найдена"));
  vi.stubGlobal("fetch", fetchMock);
  renderDetail();
  expect(await screen.findByText("Семья не найдена")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "К списку семей" })).toHaveAttribute(
    "href",
    "/admin/families",
  );
});
