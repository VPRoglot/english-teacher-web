import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));

import { LogoutButton } from "./logout-button";

const assign = vi.fn();
const realLocation = window.location;

function renderButton(logoutResponse: () => Response) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url === "/api/auth/logout") return logoutResponse();
      throw new Error(`unexpected fetch ${url}`);
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(["/api/auth/me"], { id: "u1" });
  render(
    <QueryClientProvider client={client}>
      <LogoutButton />
    </QueryClientProvider>,
  );
  return client;
}

beforeEach(() => {
  replace.mockReset();
  assign.mockReset();
  document.cookie = "csrf_token=t";
  // jsdom не умеет навигацию: подменяем location целиком, чтобы поймать assign.
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { ...realLocation, assign },
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  Object.defineProperty(window, "location", { configurable: true, value: realLocation });
  document.cookie = "csrf_token=; max-age=0";
});

test("выход — полная перезагрузка на /login, кэш очищен", async () => {
  const client = renderButton(() => new Response(null, { status: 204 }));

  await userEvent.click(screen.getByRole("button", { name: "Выйти" }));

  await waitFor(() => expect(assign).toHaveBeenCalledWith("/login"));
  expect(replace).not.toHaveBeenCalled();
  expect(client.getQueryCache().getAll()).toHaveLength(0);
});

test("ошибка выхода тоже ведёт на /login полной перезагрузкой", async () => {
  renderButton(
    () =>
      new Response(JSON.stringify({ error: { code: "internal_error", message: "Сбой", details: {} } }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      }),
  );

  await userEvent.click(screen.getByRole("button", { name: "Выйти" }));

  await waitFor(() => expect(assign).toHaveBeenCalledWith("/login"));
  expect(replace).not.toHaveBeenCalled();
});
