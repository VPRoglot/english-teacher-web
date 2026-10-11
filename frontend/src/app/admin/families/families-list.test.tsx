import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const push = vi.fn();
const replace = vi.fn();
let search = "";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace }),
  usePathname: () => "/admin/families",
  useSearchParams: () => new URLSearchParams(search),
}));

import { FamiliesList } from "./families-list";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const families = [
  {
    id: "f1",
    name: "Семья Ивановых",
    archived_at: null,
    parent_names: ["Мария Иванова", "Пётр Иванов"],
    children: [{ id: "c1", full_name: "Петя" }],
  },
  { id: "f2", name: "Семья Орловых", archived_at: null, parent_names: [], children: [] },
];

let fetchMock: ReturnType<typeof vi.fn>;

function stubApi() {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.startsWith("/api/admin/families") && init?.method === "GET") {
      return jsonResponse(200, families);
    }
    if (url === "/api/admin/families" && init?.method === "POST") {
      return jsonResponse(201, { id: "f9" });
    }
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function listUrls(): URL[] {
  return fetchMock.mock.calls
    .filter(([url, init]) => String(url).startsWith("/api/admin/families") && init?.method === "GET")
    .map(([url]) => new URL(String(url), "http://localhost"));
}

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <FamiliesList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  push.mockReset();
  replace.mockReset();
  search = "";
  document.cookie = "csrf_token=t";
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test("таблица показывает родителей и детей, строка ведёт на карточку", async () => {
  stubApi();
  renderList();
  const link = await screen.findByRole("link", { name: "Семья Ивановых" });
  expect(link).toHaveAttribute("href", "/admin/families/f1");
  const row = link.closest("tr") as HTMLElement;
  expect(within(row).getByText("Мария Иванова, Пётр Иванов")).toBeInTheDocument();
  expect(within(row).getByText("Петя")).toBeInTheDocument();
  expect(listUrls()[0].searchParams.get("archived")).toBe("false");
  expect(listUrls()[0].searchParams.has("q")).toBe(false);
});

test("поиск передаёт q в запрос и в адрес страницы", async () => {
  stubApi();
  renderList();
  await screen.findByText("Семья Ивановых");

  await userEvent.type(screen.getByRole("searchbox", { name: "Поиск" }), "анна");

  await waitFor(() => {
    const last = listUrls().at(-1);
    expect(last?.searchParams.get("q")).toBe("анна");
    expect(last?.searchParams.get("archived")).toBe("false");
  });
  // Пока человек печатает, промежуточные «а», «ан» в запрос не уходят.
  expect(
    listUrls().every((url) => !url.searchParams.has("q") || url.searchParams.get("q") === "анна"),
  ).toBe(true);
  const target = new URL(String(replace.mock.calls.at(-1)?.[0]), "http://localhost");
  expect(target.pathname).toBe("/admin/families");
  expect(target.searchParams.get("q")).toBe("анна");
});

test("параметры из адреса подставляются в запрос", async () => {
  search = "q=орлов&archived=true";
  stubApi();
  renderList();
  await screen.findByText("Семья Орловых");
  expect(screen.getByRole("searchbox", { name: "Поиск" })).toHaveValue("орлов");
  expect(screen.getByRole("checkbox", { name: "Архив" })).toBeChecked();
  expect(listUrls()[0].searchParams.get("q")).toBe("орлов");
  expect(listUrls()[0].searchParams.get("archived")).toBe("true");
});

test("переключатель «Архив» запрашивает архивные семьи", async () => {
  stubApi();
  renderList();
  await screen.findByText("Семья Ивановых");

  await userEvent.click(screen.getByRole("checkbox", { name: "Архив" }));

  await waitFor(() => expect(listUrls().at(-1)?.searchParams.get("archived")).toBe("true"));
  const target = new URL(String(replace.mock.calls.at(-1)?.[0]), "http://localhost");
  expect(target.searchParams.get("archived")).toBe("true");
});

test("создание семьи ведёт на её карточку", async () => {
  stubApi();
  renderList();
  await userEvent.click(await screen.findByRole("button", { name: "Новая семья" }));
  const dialog = await screen.findByRole("dialog");
  await userEvent.type(within(dialog).getByLabelText("Название"), "  Семья Смирновых ");
  await userEvent.type(within(dialog).getByLabelText("Комментарий"), "Пишут вечером");
  await userEvent.click(within(dialog).getByRole("button", { name: "Создать" }));

  await waitFor(() => expect(push).toHaveBeenCalledWith("/admin/families/f9"));
  const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
  expect(JSON.parse(String(post?.[1]?.body))).toEqual({
    name: "Семья Смирновых",
    tutor_comment: "Пишут вечером",
  });
});

test("после создания семьи диалог закрыт, а при повторном открытии форма пуста", async () => {
  stubApi();
  renderList();
  await userEvent.click(await screen.findByRole("button", { name: "Новая семья" }));
  const dialog = await screen.findByRole("dialog");
  await userEvent.type(within(dialog).getByLabelText("Название"), "Семья Смирновых");
  await userEvent.click(within(dialog).getByRole("button", { name: "Создать" }));

  await waitFor(() => expect(push).toHaveBeenCalledWith("/admin/families/f9"));
  // С cacheComponents прежний маршрут остаётся смонтированным (Activity): диалог не должен остаться открытым.
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

  await userEvent.click(screen.getByRole("button", { name: "Новая семья" }));
  expect(await screen.findByLabelText("Название")).toHaveValue("");
});

test("поле названия доступно по метке, а не по плейсхолдеру", async () => {
  stubApi();
  renderList();
  await userEvent.click(await screen.findByRole("button", { name: "Новая семья" }));
  const dialog = await screen.findByRole("dialog");
  const input = within(dialog).getByRole("textbox", { name: "Название" });
  expect(input).toBe(within(dialog).getByLabelText("Название"));
  expect(input).toHaveAttribute("placeholder", "Семья Ивановых");
});

test("пустое название не отправляется", async () => {
  stubApi();
  renderList();
  await userEvent.click(await screen.findByRole("button", { name: "Новая семья" }));
  const dialog = await screen.findByRole("dialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Создать" }));
  expect(await within(dialog).findByText("Введите название")).toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
});
