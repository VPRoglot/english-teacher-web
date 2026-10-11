import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useParams: () => ({ token: "tok123" }),
}));

import { AcceptInvitation } from "./accept-invitation";

const INVITATION_URL = "/api/auth/invitations/tok123";
const ACCEPT_URL = "/api/auth/invitations/tok123/accept";
const SUBMIT = "Принять приглашение";

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

const invitation = () => ({
  family_name: "Ивановы",
  expires_at: "2030-01-01T00:00:00Z",
  prefill_full_name: "Иван Иванов",
  prefill_phone: "+7 900 000-00-00",
});

const me = {
  id: "u1",
  role: "parent",
  display_name: "Иван Иванов",
  email: "ivan@example.com",
  username: null,
  family: null,
  children: [],
};

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
      <AcceptInvitation />
    </QueryClientProvider>,
  );
  return { ...view, client };
}

async function fillCredentials(password = "correct-horse-1", repeat = password) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Email"), "ivan@example.com");
  await user.type(screen.getByLabelText("Пароль"), password);
  await user.type(screen.getByLabelText("Повторите пароль"), repeat);
  return user;
}

beforeEach(() => {
  replace.mockReset();
  document.cookie = "csrf_token=t";
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test("недействительное приглашение показывает понятный текст", async () => {
  stubApi({
    [INVITATION_URL]: () => errorResponse(404, "invitation_invalid", "Приглашение недействительно"),
  });
  renderPage();
  expect(
    await screen.findByText(
      "Ссылка недействительна или устарела. Попросите репетитора прислать новую.",
    ),
  ).toBeInTheDocument();
  expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
});

test("неудачный повторный запрос приглашения не сносит форму и введённые данные", async () => {
  let failing = false;
  stubApi({
    [INVITATION_URL]: () =>
      failing ? errorResponse(500, "internal_error", "Сбой сервера") : jsonResponse(200, invitation()),
  });
  const { client } = renderPage();
  await fillCredentials();

  failing = true;
  await act(() => client.refetchQueries());
  expect(client.getQueryCache().getAll()[0]?.state.status).toBe("error");
  await act(() => new Promise((resolve) => setTimeout(resolve, 20))); // даём React перерисоваться
  expect(fetchMock).toHaveBeenCalledTimes(2); // повторный запрос действительно ушёл и упал

  expect(screen.getByLabelText("Email")).toHaveValue("ivan@example.com");
  expect(screen.getByLabelText("Пароль")).toHaveValue("correct-horse-1");
  expect(screen.queryByText("Сбой сервера")).not.toBeInTheDocument();
});

test("предзаполняет ФИО и телефон", async () => {
  stubApi({ [INVITATION_URL]: () => jsonResponse(200, invitation()) });
  renderPage();
  expect(await screen.findByText("Приглашение в семью «Ивановы»")).toBeInTheDocument();
  expect(screen.getByLabelText("ФИО")).toHaveValue("Иван Иванов");
  expect(screen.getByLabelText("Телефон")).toHaveValue("+7 900 000-00-00");
});

test("без согласия форма не отправляется", async () => {
  stubApi({ [INVITATION_URL]: () => jsonResponse(200, invitation()) });
  renderPage();
  const user = await fillCredentials();
  await user.click(screen.getByRole("button", { name: SUBMIT }));
  expect(
    await screen.findByText("Необходимо согласие на обработку персональных данных"),
  ).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1); // только GET приглашения
});

test("ссылка на политику открывается в новой вкладке", async () => {
  stubApi({ [INVITATION_URL]: () => jsonResponse(200, invitation()) });
  renderPage();
  const link = await screen.findByRole("link", { name: /персональных данных/ });
  expect(link).toHaveAttribute("href", "/privacy");
  expect(link).toHaveAttribute("target", "_blank");
});

test("пароли должны совпадать", async () => {
  stubApi({ [INVITATION_URL]: () => jsonResponse(200, invitation()) });
  renderPage();
  const user = await fillCredentials("correct-horse-1", "other-horse-2");
  await user.click(screen.getByRole("checkbox", { name: /Согласен/ }));
  await user.click(screen.getByRole("button", { name: SUBMIT }));
  expect(await screen.findByText("Пароли не совпадают")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("email_taken показывается как общая ошибка формы", async () => {
  stubApi({
    [INVITATION_URL]: () => jsonResponse(200, invitation()),
    [ACCEPT_URL]: () => errorResponse(409, "email_taken", "Этот email уже занят"),
  });
  renderPage();
  const user = await fillCredentials();
  await user.click(screen.getByRole("checkbox", { name: /Согласен/ }));
  await user.click(screen.getByRole("button", { name: SUBMIT }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Этот email уже занят");
  expect(replace).not.toHaveBeenCalled();
});

test("invalid_email показывается у поля email", async () => {
  stubApi({
    [INVITATION_URL]: () => jsonResponse(200, invitation()),
    [ACCEPT_URL]: () =>
      errorResponse(422, "invalid_email", "Некорректный email", { field: "email" }),
  });
  renderPage();
  const user = await fillCredentials();
  await user.click(screen.getByRole("checkbox", { name: /Согласен/ }));
  await user.click(screen.getByRole("button", { name: SUBMIT }));
  expect(await screen.findByText("Некорректный email")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("ошибка политики пароля показывается у поля пароля", async () => {
  stubApi({
    [INVITATION_URL]: () => jsonResponse(200, invitation()),
    [ACCEPT_URL]: () => errorResponse(422, "password_too_common", "Слишком простой пароль"),
  });
  renderPage();
  const user = await fillCredentials();
  await user.click(screen.getByRole("checkbox", { name: /Согласен/ }));
  await user.click(screen.getByRole("button", { name: SUBMIT }));
  expect(await screen.findByText("Слишком простой пароль")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("успех ведёт в кабинет и отправляет данные формы", async () => {
  stubApi({
    [INVITATION_URL]: () => jsonResponse(200, invitation()),
    [ACCEPT_URL]: () => jsonResponse(201, me),
  });
  renderPage();
  const user = await fillCredentials();
  await user.click(screen.getByRole("checkbox", { name: /Согласен/ }));
  await user.click(screen.getByRole("button", { name: SUBMIT }));
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/cabinet"));
  const acceptCall = fetchMock.mock.calls.find(([url]) => url === ACCEPT_URL);
  expect(JSON.parse(acceptCall?.[1]?.body as string)).toEqual({
    email: "ivan@example.com",
    password: "correct-horse-1",
    full_name: "Иван Иванов",
    phone: "+7 900 000-00-00",
    consent: true,
  });
  // Скрытая в <Activity> страница приглашения не должна хранить пароль.
  expect(screen.getByLabelText("Пароль")).toHaveValue("");
  expect(screen.getByLabelText("Повторите пароль")).toHaveValue("");
});
