import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const toastSuccess = vi.fn();
vi.mock("sonner", () => ({ toast: { success: (message: string) => toastSuccess(message) } }));

import { ChangePassword } from "./change-password";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function errorResponse(status: number, code: string, message: string, details = {}): Response {
  return jsonResponse(status, { error: { code, message, details } });
}

let changeResponse: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;

function renderPage() {
  fetchMock = vi.fn(async (url: string) => {
    if (url === "/api/auth/password") return changeResponse();
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ChangePassword />
    </QueryClientProvider>,
  );
}

async function fillAndSubmit(current = "old-pass-1", next = "new-pass-123", repeat = next) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Текущий пароль"), current);
  await user.type(screen.getByLabelText("Новый пароль"), next);
  await user.type(screen.getByLabelText("Повторите новый пароль"), repeat);
  await user.click(screen.getByRole("button", { name: "Сменить пароль" }));
}

beforeEach(() => {
  toastSuccess.mockReset();
  document.cookie = "csrf_token=t";
  changeResponse = () => new Response(null, { status: 204 });
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test("успешная смена пароля: тост и сброс формы", async () => {
  renderPage();
  await fillAndSubmit();
  await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Пароль изменён"));
  const init = fetchMock.mock.calls[0][1] as RequestInit;
  expect(JSON.parse(String(init.body))).toEqual({
    current_password: "old-pass-1",
    new_password: "new-pass-123",
  });
  expect(screen.getByLabelText("Текущий пароль")).toHaveValue("");
  expect(screen.getByLabelText("Новый пароль")).toHaveValue("");
  expect(screen.getByLabelText("Повторите новый пароль")).toHaveValue("");
});

test("неверный текущий пароль под полем", async () => {
  changeResponse = () =>
    errorResponse(422, "invalid_current_password", "Неверный текущий пароль", {
      field: "current_password",
    });
  renderPage();
  await fillAndSubmit();
  expect(await screen.findByText("Неверный текущий пароль")).toBeInTheDocument();
  expect(toastSuccess).not.toHaveBeenCalled();
});

test("ошибка политики пароля под полем нового пароля", async () => {
  changeResponse = () => errorResponse(422, "password_too_common", "Пароль слишком простой");
  renderPage();
  await fillAndSubmit();
  expect(await screen.findByText("Пароль слишком простой")).toBeInTheDocument();
});

test("новые пароли должны совпадать", async () => {
  renderPage();
  await fillAndSubmit("old-pass-1", "new-pass-123", "other-pass-123");
  expect(await screen.findByText("Пароли не совпадают")).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
});
