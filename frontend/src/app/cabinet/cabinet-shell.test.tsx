import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const replace = vi.fn();
let pathname = "/cabinet";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => pathname,
  useSearchParams: () => new URLSearchParams(),
}));

import { CabinetShell } from "./cabinet-shell";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

type Kid = { id: string; full_name: string };

const me = (role: "tutor" | "parent" | "child", children: Kid[]) => ({
  id: "u1",
  role,
  display_name: "Мария",
  email: null,
  username: null,
  family: null,
  children,
});

let fetchMock: ReturnType<typeof vi.fn>;

function renderShell(role: "tutor" | "parent" | "child", children: Kid[] = []) {
  fetchMock = vi.fn(async (url: string) => {
    if (url === "/api/auth/me") return jsonResponse(200, me(role, children));
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <CabinetShell>
        <p>содержимое</p>
      </CabinetShell>
    </QueryClientProvider>,
  );
  return client;
}

beforeEach(() => {
  replace.mockReset();
  pathname = "/cabinet";
  document.cookie = "csrf_token=t";
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test("родитель видит вкладку «Дети», активна текущая", async () => {
  pathname = "/cabinet/settings";
  renderShell("parent");
  expect(await screen.findByRole("link", { name: "Дети" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Настройки" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "Главная" })).not.toHaveAttribute("aria-current");
  expect(screen.getByText("Мария")).toBeInTheDocument();
  expect(screen.getByText("содержимое")).toBeInTheDocument();
});

test("у ребёнка нет вкладки «Дети»", async () => {
  renderShell("child");
  expect(await screen.findByRole("link", { name: "Настройки" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Дети" })).not.toBeInTheDocument();
});

test("навигация родителя: главная, календарь, дети, настройки", async () => {
  renderShell("parent");
  await screen.findByRole("link", { name: "Дети" });
  const nav = within(screen.getByRole("navigation", { name: "Основная навигация" }));
  expect(nav.getAllByRole("link").map((link) => link.textContent)).toEqual([
    "Главная",
    "Календарь",
    "Дети",
    "Настройки",
  ]);
  expect(nav.getByRole("link", { name: "Календарь" })).toHaveAttribute("href", "/cabinet/calendar");
});

test("у ребёнка есть «Календарь», активна текущая вкладка", async () => {
  pathname = "/cabinet/calendar";
  renderShell("child");
  expect(await screen.findByRole("link", { name: "Календарь" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(screen.getByRole("link", { name: "Главная" })).not.toHaveAttribute("aria-current");
});

test("репетитора перенаправляет в админку, содержимое не показывается", async () => {
  renderShell("tutor");
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin"));
  expect(screen.queryByText("содержимое")).not.toBeInTheDocument();
});

test("в шапке родителя с несколькими детьми есть переключатель ребёнка", async () => {
  renderShell("parent", [
    { id: "c1", full_name: "Петя" },
    { id: "c2", full_name: "Маша" },
  ]);
  expect(await screen.findByRole("combobox", { name: "Ребёнок" })).toBeInTheDocument();
});

test("у родителя с одним ребёнком переключателя нет", async () => {
  renderShell("parent", [{ id: "c1", full_name: "Петя" }]);
  await screen.findByRole("link", { name: "Дети" });
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
});

// Само поведение выхода (полная перезагрузка на /login) — в components/logout-button.test.tsx.
test("в шапке есть кнопка выхода", async () => {
  renderShell("parent");
  expect(await screen.findByRole("button", { name: "Выйти" })).toBeInTheDocument();
});
