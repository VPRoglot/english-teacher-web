import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const replace = vi.fn();
const toastSuccess = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));
vi.mock("sonner", () => ({ toast: { success: (message: string) => toastSuccess(message) } }));

import { ChildrenAccounts } from "./children-accounts";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function errorResponse(status: number, code: string, message: string, details = {}): Response {
  return jsonResponse(status, { error: { code, message, details } });
}

const me = (role: "parent" | "child") => ({
  id: "u1",
  role,
  display_name: "Мария",
  email: null,
  username: null,
  family: { id: "f1", name: "Семья Ивановых" },
  children: [],
});

type Child = { id: string; full_name: string; birth_year: null; english_level: null; username: string | null };

let children: Child[];
let accountPost: (body: { username: string; password: string }) => Response;
let fetchMock: ReturnType<typeof vi.fn>;

function stubApi(role: "parent" | "child" = "parent") {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/auth/me") return jsonResponse(200, me(role));
    if (url === "/api/me/children") return jsonResponse(200, children);
    if (url === "/api/me/children/c1/account" && init?.method === "POST") {
      return accountPost(JSON.parse(String(init.body)));
    }
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ChildrenAccounts />
    </QueryClientProvider>,
  );
}

async function fillCard(name: string, username: string, password: string) {
  const user = userEvent.setup();
  const card = (await screen.findByText(name)).closest("[data-slot=card]") as HTMLElement;
  const login = within(card).getByLabelText("Логин");
  await user.clear(login);
  await user.type(login, username);
  await user.type(within(card).getByLabelText("Пароль"), password);
  await user.click(within(card).getByRole("button", { name: "Сохранить" }));
  return card;
}

beforeEach(() => {
  replace.mockReset();
  toastSuccess.mockReset();
  document.cookie = "csrf_token=t";
  children = [{ id: "c1", full_name: "Петя", birth_year: null, english_level: null, username: null }];
  accountPost = () => jsonResponse(200, children[0]);
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test("родитель задаёт логин ребёнку", async () => {
  accountPost = (body) => {
    children = [{ ...children[0], username: body.username }];
    return jsonResponse(200, children[0]);
  };
  stubApi();
  renderPage();
  expect(await screen.findByText("Логин не выдан")).toBeInTheDocument();

  await fillCard("Петя", "  petya  ", "secret1");

  await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Логин сохранён"));
  const post = fetchMock.mock.calls.find(([url]) => url === "/api/me/children/c1/account");
  expect(JSON.parse(String(post?.[1]?.body))).toEqual({ username: "petya", password: "secret1" });
  expect(await screen.findByText("Логин: petya")).toBeInTheDocument();
  expect(screen.queryByText("Логин не выдан")).not.toBeInTheDocument();
});

test("ошибка username_taken под полем логина", async () => {
  accountPost = () => errorResponse(409, "username_taken", "Этот логин уже занят", { field: "username" });
  stubApi();
  renderPage();
  const card = await fillCard("Петя", "petya", "secret1");
  expect(await within(card).findByText("Этот логин уже занят")).toBeInTheDocument();
  expect(toastSuccess).not.toHaveBeenCalled();
});

test("ошибка политики пароля под полем пароля", async () => {
  accountPost = () => errorResponse(422, "password_too_common", "Пароль слишком простой");
  stubApi();
  renderPage();
  const card = await fillCard("Петя", "petya", "secret1");
  expect(await within(card).findByText("Пароль слишком простой")).toBeInTheDocument();
});

test("короткий пароль не отправляется", async () => {
  stubApi();
  renderPage();
  const card = await fillCard("Петя", "petya", "12345");
  expect(await within(card).findByText("Минимум 6 символов")).toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([url]) => url === "/api/me/children/c1/account")).toBe(false);
});

test("ребёнка перенаправляет в кабинет", async () => {
  stubApi("child");
  renderPage();
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/cabinet"));
  expect(fetchMock.mock.calls.some(([url]) => url === "/api/me/children")).toBe(false);
});
