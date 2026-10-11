import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const replace = vi.fn();
let search = "";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams(search),
}));

import { LoginForm } from "./login-form";

type Handler = () => Response;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function errorResponse(status: number, code: string, message: string, details = {}): Response {
  return jsonResponse(status, { error: { code, message, details } });
}

const me = (role: "tutor" | "parent" | "student") => ({
  id: "u1",
  role,
  display_name: "Иван",
  email: null,
  username: "ivan",
  family: null,
  children: [],
});

const unauthenticated = () => errorResponse(401, "unauthenticated", "Требуется вход");

let fetchMock: ReturnType<typeof vi.fn>;

function stubApi(routes: Record<string, Handler>) {
  fetchMock = vi.fn(async (url: string) => {
    const handler = routes[url];
    if (!handler) throw new Error(`unexpected fetch ${url}`);
    return handler();
  });
  vi.stubGlobal("fetch", fetchMock);
}

function renderForm() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LoginForm />
    </QueryClientProvider>,
  );
}

async function fillAndSubmit(login = "ivan", password = "secret") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email или логин"), login);
  await user.type(screen.getByLabelText("Пароль"), password);
  await user.click(screen.getByRole("button", { name: "Войти" }));
}

beforeEach(() => {
  search = "";
  replace.mockReset();
  document.cookie = "csrf_token=t";
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test("успешный вход ведёт на next, если он безопасен", async () => {
  search = "next=/cabinet/settings";
  stubApi({
    "/api/auth/me": unauthenticated,
    "/api/auth/login": () => jsonResponse(200, me("parent")),
  });
  renderForm();
  await fillAndSubmit();
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/cabinet/settings"));
});

test("без next вход ведёт на главную страницу роли", async () => {
  stubApi({
    "/api/auth/me": unauthenticated,
    "/api/auth/login": () => jsonResponse(200, me("parent")),
  });
  renderForm();
  await fillAndSubmit();
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/cabinet"));
});

test("опасный next игнорируется", async () => {
  search = "next=//evil.com";
  stubApi({
    "/api/auth/me": unauthenticated,
    "/api/auth/login": () => jsonResponse(200, me("tutor")),
  });
  renderForm();
  await fillAndSubmit();
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin"));
});

test("неверный пароль показывает общую ошибку", async () => {
  stubApi({
    "/api/auth/me": unauthenticated,
    "/api/auth/login": () => errorResponse(401, "invalid_credentials", "Неверные данные"),
  });
  renderForm();
  await fillAndSubmit();
  expect(await screen.findByRole("alert")).toHaveTextContent("Неверный логин или пароль");
  expect(replace).not.toHaveBeenCalled();
});

test("лимит попыток показывает минуты", async () => {
  stubApi({
    "/api/auth/me": unauthenticated,
    "/api/auth/login": () =>
      errorResponse(429, "rate_limited", "Слишком часто", { retry_after: 600 }),
  });
  renderForm();
  await fillAndSubmit();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Слишком много попыток. Попробуйте через 10 мин.",
  );
});

test("прочие ошибки показывают сообщение сервера", async () => {
  stubApi({
    "/api/auth/me": unauthenticated,
    "/api/auth/login": () => errorResponse(500, "internal_error", "Сбой сервера"),
  });
  renderForm();
  await fillAndSubmit();
  expect(await screen.findByRole("alert")).toHaveTextContent("Сбой сервера");
});

test("пустые поля не отправляются", async () => {
  stubApi({ "/api/auth/me": unauthenticated });
  renderForm();
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1)); // проба /me
  await userEvent.click(screen.getByRole("button", { name: "Войти" }));
  expect(await screen.findByText("Введите email или логин")).toBeInTheDocument();
  expect(screen.getByText("Введите пароль")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("кнопка заблокирована на время запроса", async () => {
  let release: (response: Response) => void = () => {};
  const pending = new Promise<Response>((resolve) => (release = resolve));
  fetchMock = vi.fn(async (url: string) => {
    if (url === "/api/auth/me") return unauthenticated();
    return pending;
  });
  vi.stubGlobal("fetch", fetchMock);
  renderForm();
  await fillAndSubmit();
  await waitFor(() => expect(screen.getByRole("button", { name: "Входим…" })).toBeDisabled());
  release(jsonResponse(200, me("tutor")));
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin"));
});

test("уже авторизованного сразу перенаправляет на главную роли", async () => {
  stubApi({ "/api/auth/me": () => jsonResponse(200, me("tutor")) });
  renderForm();
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin"));
});
