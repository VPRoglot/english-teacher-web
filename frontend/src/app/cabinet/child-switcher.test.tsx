import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const replace = vi.fn();
let pathname = "/cabinet/calendar";
let search = "";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => pathname,
  useSearchParams: () => new URLSearchParams(search),
}));

import { ChildSwitcher } from "./child-switcher";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const KIDS = [
  { id: "c1", full_name: "Петя" },
  { id: "c2", full_name: "Маша" },
];

function renderSwitcher(role: "parent" | "child", children = KIDS) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url === "/api/auth/me") {
        return jsonResponse(200, {
          id: "u1",
          role,
          display_name: "Мария",
          email: null,
          username: null,
          family: null,
          children,
        });
      }
      throw new Error(`unexpected fetch ${url}`);
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ChildSwitcher />
      <p>после</p>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  replace.mockReset();
  pathname = "/cabinet/calendar";
  search = "";
  document.cookie = "csrf_token=t";
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test("hidden for one child and for child role", async () => {
  const one = renderSwitcher("parent", [KIDS[0]!]);
  await screen.findByText("после");
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  one.unmount();

  renderSwitcher("child", KIDS);
  await screen.findByText("после");
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
});

test("parent with several children sees all-children option and names", async () => {
  renderSwitcher("parent");
  const select = await screen.findByRole("combobox", { name: "Ребёнок" });
  expect(select).toHaveValue("");
  expect(Array.from((select as HTMLSelectElement).options).map((o) => o.text)).toEqual([
    "Все дети",
    "Петя",
    "Маша",
  ]);
});

test("selecting a child writes ?child= and keeps other params", async () => {
  search = "view=week";
  renderSwitcher("parent");
  await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Ребёнок" }), "c2");
  expect(replace).toHaveBeenCalledWith("/cabinet/calendar?view=week&child=c2");
});

test("selecting all children removes only the child param", async () => {
  search = "child=c2&view=week";
  renderSwitcher("parent");
  const select = await screen.findByRole("combobox", { name: "Ребёнок" });
  expect(select).toHaveValue("c2");
  await userEvent.selectOptions(select, "");
  expect(replace).toHaveBeenCalledWith("/cabinet/calendar?view=week");
});

test("selecting all children with no other params leaves a bare path", async () => {
  search = "child=c1";
  renderSwitcher("parent");
  await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Ребёнок" }), "");
  expect(replace).toHaveBeenCalledWith("/cabinet/calendar");
});

test("unknown child id falls back to all", async () => {
  search = "child=zzz";
  renderSwitcher("parent");
  expect(await screen.findByRole("combobox", { name: "Ребёнок" })).toHaveValue("");
});
