import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useParams: () => ({ token: "tok123" }),
}));

import { ResetPassword } from "./reset-password";

const RESET_URL = "/api/auth/password-resets/tok123";

type Handler = (init?: RequestInit) => Response;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function errorResponse(status: number, code: string, message: string, details = {}): Response {
  return jsonResponse(status, { error: { code, message, details } });
}

const info = () => jsonResponse(200, { expires_at: "2030-01-01T00:00:00Z", login: "masha" });

let fetchMock: ReturnType<typeof vi.fn>;

function stubApi(routes: Record<string, Handler>) {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const handler = routes[url];
    if (!handler) throw new Error(`unexpected fetch ${url}`);
    return handler(init);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <ResetPassword />
    </QueryClientProvider>,
  );
  return { ...view, client };
}

async function fillAndSubmit(password = "correct-horse-1", repeat = password) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Новый пароль"), password);
  await user.type(screen.getByLabelText("Повторите пароль"), repeat);
  await user.click(screen.getByRole("button", { name: "Сменить пароль" }));
}

beforeEach(() => {
  document.cookie = "csrf_token=t";
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test("сброс: успех показывает «Пароль изменён» и ссылку на вход", async () => {
  stubApi({
    [RESET_URL]: (init) => (init?.method === "POST" ? new Response(null, { status: 204 }) : info()),
  });
  renderPage();
  expect(await screen.findByText("Новый пароль для masha")).toBeInTheDocument();
  await fillAndSubmit();
  expect(await screen.findByText("Пароль изменён")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Войти" })).toHaveAttribute("href", "/login");
  const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
  expect(JSON.parse(post?.[1]?.body as string)).toEqual({ password: "correct-horse-1" });
});

test("сброс: экран успеха переживает повторный запрос погашенного токена", async () => {
  let consumed = false;
  stubApi({
    [RESET_URL]: (init) => {
      if (init?.method === "POST") {
        consumed = true;
        return new Response(null, { status: 204 });
      }
      return consumed ? errorResponse(404, "reset_invalid", "Ссылка недействительна") : info();
    },
  });
  const { client } = renderPage();
  await fillAndSubmit();
  expect(await screen.findByText("Пароль изменён")).toBeInTheDocument();

  await act(() => client.refetchQueries());
  expect(client.getQueryCache().getAll()[0]?.state.status).toBe("error");
  await act(() => new Promise((resolve) => setTimeout(resolve, 20))); // даём React перерисоваться
  const gets = fetchMock.mock.calls.filter(([, init]) => init?.method !== "POST");
  expect(gets).toHaveLength(2); // повторный запрос действительно ушёл и получил 404

  expect(screen.getByText("Пароль изменён")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Войти" })).toHaveAttribute("href", "/login");
  expect(screen.queryByText(/недействительна/)).not.toBeInTheDocument();
});

test("сброс: недействительная ссылка", async () => {
  stubApi({ [RESET_URL]: () => errorResponse(404, "reset_invalid", "Ссылка недействительна") });
  renderPage();
  expect(
    await screen.findByText(
      "Ссылка для смены пароля недействительна или устарела. Попросите репетитора прислать новую.",
    ),
  ).toBeInTheDocument();
  expect(screen.queryByLabelText("Новый пароль")).not.toBeInTheDocument();
});

test("сброс: пароли должны совпадать", async () => {
  stubApi({ [RESET_URL]: info });
  renderPage();
  await fillAndSubmit("correct-horse-1", "other-horse-2");
  expect(await screen.findByText("Пароли не совпадают")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("сброс: ошибка политики пароля показывается у поля", async () => {
  stubApi({
    [RESET_URL]: (init) =>
      init?.method === "POST"
        ? errorResponse(422, "password_too_short", "Пароль слишком короткий")
        : info(),
  });
  renderPage();
  await fillAndSubmit();
  expect(await screen.findByText("Пароль слишком короткий")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("сброс: прочие ошибки показываются над кнопкой", async () => {
  stubApi({
    [RESET_URL]: (init) =>
      init?.method === "POST" ? errorResponse(500, "internal_error", "Сбой сервера") : info(),
  });
  renderPage();
  await fillAndSubmit();
  expect(await screen.findByRole("alert")).toHaveTextContent("Сбой сервера");
});
