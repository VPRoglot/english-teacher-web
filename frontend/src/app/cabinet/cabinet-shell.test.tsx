import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const replace = vi.fn();
let pathname = "/cabinet";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => pathname,
}));

import { CabinetShell } from "./cabinet-shell";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const me = (role: "tutor" | "parent" | "child") => ({
  id: "u1",
  role,
  display_name: "Мария",
  email: null,
  username: null,
  family: null,
  children: [],
});

let fetchMock: ReturnType<typeof vi.fn>;

function renderShell(role: "tutor" | "parent" | "child") {
  fetchMock = vi.fn(async (url: string) => {
    if (url === "/api/auth/me") return jsonResponse(200, me(role));
    if (url === "/api/auth/logout") return new Response(null, { status: 204 });
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

test("репетитора перенаправляет в админку, содержимое не показывается", async () => {
  renderShell("tutor");
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin"));
  expect(screen.queryByText("содержимое")).not.toBeInTheDocument();
});

test("выход очищает кэш и ведёт на /login", async () => {
  const client = renderShell("parent");
  await userEvent.click(await screen.findByRole("button", { name: "Выйти" }));
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  expect(client.getQueryCache().getAll()).toHaveLength(0);
});
