import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const replace = vi.fn();
const pathname = "/admin/families/f1";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => pathname,
}));

import { AdminShell } from "./admin-shell";

function renderShell(role: "tutor" | "parent") {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            id: "u1",
            role,
            display_name: "Репетитор",
            email: null,
            username: null,
            family: null,
            children: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
    ),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <AdminShell>
        <p>содержимое</p>
      </AdminShell>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  replace.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("репетитор видит навигацию, «Семьи» активна на карточке семьи", async () => {
  renderShell("tutor");
  expect(await screen.findByText("содержимое")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Обзор" })).not.toHaveAttribute("aria-current");
  expect(screen.getByRole("link", { name: "Семьи" })).toHaveAttribute("aria-current", "page");
  expect(replace).not.toHaveBeenCalled();
});

test("навигация репетитора: обзор, календарь, заявки, семьи, сайт, настройки", async () => {
  renderShell("tutor");
  await screen.findByText("содержимое");
  const nav = within(screen.getByRole("navigation", { name: "Основная навигация" }));
  expect(nav.getAllByRole("link").map((link) => link.textContent)).toEqual([
    "Обзор",
    "Календарь",
    "Запросы",
    "Заявки",
    "Семьи",
    "Сайт",
    "Настройки",
  ]);
  expect(nav.getByRole("link", { name: "Календарь" })).toHaveAttribute("href", "/admin/calendar");
  expect(nav.getByRole("link", { name: "Запросы" })).toHaveAttribute("href", "/admin/requests");
  expect(nav.getByRole("link", { name: "Настройки" })).toHaveAttribute("href", "/admin/settings");
});

test("не репетитора перенаправляет в кабинет, содержимое не показывается", async () => {
  renderShell("parent");
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/cabinet"));
  expect(screen.queryByText("содержимое")).not.toBeInTheDocument();
});
