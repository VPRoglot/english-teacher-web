import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const push = vi.fn();
const replace = vi.fn();
let search = "";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace }),
  usePathname: () => "/admin/leads",
  useSearchParams: () => new URLSearchParams(search),
}));

import { LeadsList } from "./leads-list";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const items = [
  {
    id: "l1",
    created_at: "2026-10-10T09:30:00Z",
    parent_name: "Мария Иванова",
    child_name: "Петя",
    child_age: 9,
    contact_method: "telegram",
    messenger_handle: "@maria",
    phone: "+79991234567",
    status: "new",
  },
  {
    id: "l2",
    created_at: "2026-10-09T10:00:00Z",
    parent_name: "Ольга Орлова",
    child_name: "Саша",
    child_age: 12,
    contact_method: "whatsapp",
    messenger_handle: null,
    phone: "+79990001122",
    status: "trial_scheduled",
  },
];

let tutorTimeZone = "Europe/Moscow";
let fetchMock: ReturnType<typeof vi.fn>;

function stubApi(body: { items: unknown[]; total: number } = { items, total: items.length }) {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.startsWith("/api/admin/leads") && init?.method === "GET") {
      return jsonResponse(200, body);
    }
    if (url === "/api/admin/settings") {
      return jsonResponse(200, { timezone: tutorTimeZone, cancel_policy_hours: 24 });
    }
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function listUrls(): string[] {
  return fetchMock.mock.calls
    .filter(([url, init]) => String(url).startsWith("/api/admin/leads") && init?.method === "GET")
    .map(([url]) => String(url));
}

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LeadsList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  push.mockReset();
  replace.mockReset();
  search = "";
  tutorTimeZone = "Europe/Moscow";
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("renders leads with status labels and links", async () => {
  stubApi();
  renderList();

  const rows = await screen.findAllByRole("row");
  const first = within(rows[1]);
  expect(first.getByRole("link", { name: "Мария Иванова" })).toHaveAttribute(
    "href",
    "/admin/leads/l1",
  );
  expect(first.getByText("Петя, 9")).toBeInTheDocument();
  expect(first.getByText("10.10.2026 12:30")).toBeInTheDocument();
  expect(first.getByText("Новая")).toBeInTheDocument();
  expect(first.getByRole("link", { name: "Telegram · +79991234567" })).toHaveAttribute(
    "href",
    "https://t.me/maria",
  );

  const second = within(rows[2]);
  expect(second.getByText("Пробное назначено")).toBeInTheDocument();
  expect(second.getByRole("link", { name: "WhatsApp · +79990001122" })).toHaveAttribute(
    "href",
    "https://wa.me/79990001122",
  );
  expect(listUrls()).toEqual(["/api/admin/leads?limit=50&offset=0"]);
});

test("dates are shown in the tutor time zone from settings", async () => {
  tutorTimeZone = "Asia/Yekaterinburg";
  stubApi();
  renderList();

  const rows = await screen.findAllByRole("row");
  expect(await within(rows[1]).findByText("10.10.2026 14:30")).toBeInTheDocument();
  expect(within(rows[1]).queryByText("10.10.2026 12:30")).not.toBeInTheDocument();
});

test("status filter and search go to the URL and the API", async () => {
  stubApi();
  renderList();
  await screen.findByText("Мария Иванова");

  await userEvent.click(screen.getByRole("combobox", { name: "Статус" }));
  await userEvent.click(await screen.findByRole("option", { name: "Отказ" }));

  await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin/leads?status=rejected"));
  await waitFor(() =>
    expect(listUrls()).toContain("/api/admin/leads?status=rejected&limit=50&offset=0"),
  );

  await userEvent.type(screen.getByRole("searchbox", { name: "Поиск" }), "Орлова");
  await waitFor(() =>
    expect(replace).toHaveBeenLastCalledWith("/admin/leads?status=rejected&q=%D0%9E%D1%80%D0%BB%D0%BE%D0%B2%D0%B0"),
  );
  // Пока набирается слово, лишних запросов нет: debounce склеивает ввод в один.
  expect(listUrls().filter((url) => url.includes("q="))).toEqual([
    "/api/admin/leads?status=rejected&q=%D0%9E%D1%80%D0%BB%D0%BE%D0%B2%D0%B0&limit=50&offset=0",
  ]);
});

test("initial state is read from the URL", async () => {
  search = "status=contacted&q=Иван";
  stubApi();
  renderList();

  await screen.findByText("Мария Иванова");
  expect(screen.getByRole("searchbox", { name: "Поиск" })).toHaveValue("Иван");
  expect(screen.getByRole("combobox", { name: "Статус" })).toHaveTextContent("Связались");
  expect(listUrls()[0]).toBe(
    "/api/admin/leads?status=contacted&q=%D0%98%D0%B2%D0%B0%D0%BD&limit=50&offset=0",
  );
  expect(replace).not.toHaveBeenCalled();
});

test("pagination uses offset", async () => {
  search = "page=2";
  stubApi({ items, total: 120 });
  renderList();

  await screen.findByText("Мария Иванова");
  expect(listUrls()).toEqual(["/api/admin/leads?limit=50&offset=50"]);
  expect(screen.getByText("51–52 из 120")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Назад" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Дальше" })).toBeEnabled();

  await userEvent.click(screen.getByRole("button", { name: "Дальше" }));
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin/leads?page=3"));
  await waitFor(() => expect(listUrls()).toContain("/api/admin/leads?limit=50&offset=100"));
  await waitFor(() => expect(screen.getByRole("button", { name: "Дальше" })).toBeDisabled());
});

test("Назад from the second page returns to a clean URL", async () => {
  search = "page=2";
  stubApi({ items, total: 120 });
  renderList();
  await screen.findByText("Мария Иванова");

  await userEvent.click(screen.getByRole("button", { name: "Назад" }));
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin/leads"));
  await waitFor(() => expect(listUrls()).toContain("/api/admin/leads?limit=50&offset=0"));
  await waitFor(() => expect(screen.getByRole("button", { name: "Назад" })).toBeDisabled());
});

test("no pager for a short list", async () => {
  stubApi();
  renderList();
  await screen.findByText("Мария Иванова");
  expect(screen.queryByRole("button", { name: "Дальше" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Назад" })).not.toBeInTheDocument();
});

test("changing the filter returns to the first page", async () => {
  search = "page=2";
  stubApi({ items, total: 120 });
  renderList();
  await screen.findByText("Мария Иванова");

  await userEvent.click(screen.getByRole("combobox", { name: "Статус" }));
  await userEvent.click(await screen.findByRole("option", { name: "Новая" }));

  await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin/leads?status=new"));
  await waitFor(() => expect(listUrls()).toContain("/api/admin/leads?status=new&limit=50&offset=0"));
});

test("empty states", async () => {
  stubApi({ items: [], total: 0 });
  const { unmount } = renderList();
  expect(await screen.findByText("Заявок пока нет")).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  unmount();

  search = "status=rejected";
  stubApi({ items: [], total: 0 });
  renderList();
  expect(await screen.findByText("Ничего не найдено")).toBeInTheDocument();
});

test("shows an error message when loading fails", async () => {
  fetchMock = vi.fn(async () => jsonResponse(500, { error: { code: "internal", message: "Сбой сервера" } }));
  vi.stubGlobal("fetch", fetchMock);
  renderList();
  expect(await screen.findByText("Сбой сервера")).toBeInTheDocument();
});
