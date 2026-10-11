import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

type CaptchaProps = {
  sitekey: string;
  visible?: boolean;
  onSuccess?: (token: string) => void;
  onChallengeHidden?: () => void;
  onNetworkError?: () => void;
  onTokenExpired?: () => void;
  onJavascriptError?: (error: { filename: string; message: string; col: number; line: number }) => void;
};

const captcha = vi.hoisted(() => ({
  autoSolve: true,
  props: null as CaptchaProps | null,
}));
const captchaProps = vi.fn();
vi.mock("@yandex/smart-captcha", () => ({
  InvisibleSmartCaptcha: (props: CaptchaProps) => {
    captchaProps(props.sitekey);
    const { visible, onSuccess } = props;
    useEffect(() => {
      captcha.props = props;
    });
    useEffect(() => {
      if (visible && captcha.autoSolve) onSuccess?.("tok");
    }, [visible, onSuccess]);
    return <div data-testid="captcha" />;
  },
}));

import { TrialForm } from "./trial-form";

const PHONE_ERROR = "Укажите телефон в формате +7 999 123-45-67";

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

function errorResponse(
  status: number,
  code: string,
  message: string,
  details: Record<string, unknown> = {},
  headers: Record<string, string> = {},
) {
  return jsonResponse(status, { error: { code, message, details } }, headers);
}

let fetchMock: ReturnType<typeof vi.fn>;

function stubApi(respond: () => Response = () => jsonResponse(201, { accepted: true })) {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/public/leads" && init?.method === "POST") return respond();
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function postBody(): Record<string, unknown> {
  const calls = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
  expect(calls).toHaveLength(1);
  return JSON.parse(String(calls[0][1].body));
}

function renderForm(captchaKey: string | null = null) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TrialForm captchaKey={captchaKey} />
    </QueryClientProvider>,
  );
}

const phoneInput = () => screen.getByRole("textbox", { name: "Телефон" });
const submitButton = () => screen.getByRole("button", { name: "Записаться на пробное" });

async function fillRequired(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Ваше имя"), "Мария");
  await user.type(screen.getByLabelText("Имя ребёнка"), "Саша");
  await user.type(screen.getByLabelText("Возраст ребёнка"), "9");
  await user.type(phoneInput(), "89991234567");
  await user.click(screen.getByRole("checkbox", { name: /Согласен/ }));
}

beforeEach(() => {
  document.cookie = "csrf_token=t";
  sessionStorage.clear();
  captchaProps.mockClear();
  captcha.autoSolve = true;
  captcha.props = null;
  stubApi();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test("requires consent and shows field errors before sending", async () => {
  const user = userEvent.setup();
  renderForm();

  await user.click(submitButton());

  expect(await screen.findByText("Необходимо согласие на обработку персональных данных")).toBeInTheDocument();
  expect(screen.getAllByText("Заполните поле").length).toBeGreaterThanOrEqual(2);
  expect(fetchMock).not.toHaveBeenCalled();
});

test("child age outside 3-18 is rejected on the client", async () => {
  const user = userEvent.setup();
  renderForm();

  await fillRequired(user);
  const age = screen.getByLabelText("Возраст ребёнка");
  await user.clear(age);
  await user.type(age, "2");
  await user.click(submitButton());

  expect(await screen.findByText("Возраст — от 3 до 18 лет")).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
});

test("phone input is masked as you type", async () => {
  const user = userEvent.setup();
  renderForm();

  await user.type(phoneInput(), "89991234567");

  expect(phoneInput()).toHaveValue("+7 (999) 123-45-67");
});

test("telegram handle field appears only for Telegram", async () => {
  const user = userEvent.setup();
  renderForm();

  expect(screen.getByRole("radio", { name: "Telegram" })).toBeChecked();
  expect(screen.getByLabelText("Ник в Telegram")).toBeInTheDocument();

  await user.click(screen.getByRole("radio", { name: "WhatsApp" }));
  expect(screen.queryByLabelText("Ник в Telegram")).toBeNull();

  await user.click(screen.getByRole("radio", { name: "Телефон" }));
  expect(screen.queryByLabelText("Ник в Telegram")).toBeNull();

  await user.click(screen.getByRole("radio", { name: "Telegram" }));
  expect(screen.getByLabelText("Ник в Telegram")).toBeInTheDocument();
});

test("submits lead with utm and shows thank-you", async () => {
  sessionStorage.setItem("utm", JSON.stringify({ utm_source: "vk", utm_campaign: "autumn" }));
  const user = userEvent.setup();
  renderForm();

  await fillRequired(user);
  await user.type(screen.getByLabelText("Ник в Telegram"), "@masha");
  await user.type(screen.getByLabelText("Цель занятий"), "Подготовка к школе");
  await user.click(submitButton());

  expect(await screen.findByText(/Спасибо! Заявка отправлена/)).toHaveTextContent(
    "Спасибо! Заявка отправлена — я свяжусь с вами в ближайшее время.",
  );
  const body = postBody();
  expect(body).toEqual({
    parent_name: "Мария",
    child_name: "Саша",
    child_age: 9,
    phone: "+7 (999) 123-45-67",
    contact_method: "telegram",
    messenger_handle: "@masha",
    goal: "Подготовка к школе",
    preferred_time: null,
    consent: true,
    utm_source: "vk",
    utm_campaign: "autumn",
  });
  expect(screen.queryByRole("button", { name: "Записаться на пробное" })).toBeNull();
});

test("handle is not sent for other contact methods", async () => {
  const user = userEvent.setup();
  renderForm();

  await fillRequired(user);
  await user.type(screen.getByLabelText("Ник в Telegram"), "@masha");
  await user.click(screen.getByRole("radio", { name: "WhatsApp" }));
  await user.click(submitButton());

  await screen.findByText(/Спасибо! Заявка отправлена/);
  expect(postBody()).toMatchObject({ contact_method: "whatsapp", messenger_handle: null });
});

test("honeypot is hidden from people and assistive tech but filled value is sent", async () => {
  const user = userEvent.setup();
  const { container } = renderForm();

  const honeypot = container.querySelector<HTMLInputElement>('input[name="website"]');
  expect(honeypot).not.toBeNull();
  expect(honeypot).toHaveAttribute("tabindex", "-1");
  expect(honeypot).toHaveAttribute("autocomplete", "off");
  expect(honeypot?.closest("[aria-hidden='true']")).not.toBeNull();

  await fillRequired(user);
  await user.type(honeypot!, "http://spam.example");
  await user.click(submitButton());

  await screen.findByText(/Спасибо! Заявка отправлена/);
  expect(postBody()).toMatchObject({ website: "http://spam.example" });
});

test("429 shows friendly message and keeps values", async () => {
  stubApi(() => errorResponse(429, "rate_limited", "Слишком много запросов", {}, { "Retry-After": "3600" }));
  const user = userEvent.setup();
  renderForm();

  await fillRequired(user);
  await user.click(submitButton());

  expect(
    await screen.findByText(
      "Слишком много заявок с этого устройства. Попробуйте позже или напишите напрямую.",
    ),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Ваше имя")).toHaveValue("Мария");
  expect(phoneInput()).toHaveValue("+7 (999) 123-45-67");
  expect(screen.getByRole("checkbox", { name: /Согласен/ })).toBeChecked();
  expect(submitButton()).toBeEnabled();
});

test("422 lands on the phone field", async () => {
  stubApi(() =>
    errorResponse(422, "validation_error", "Проверьте данные", {
      fields: [{ loc: ["body", "phone"], message: PHONE_ERROR }],
    }),
  );
  const user = userEvent.setup();
  renderForm();

  await fillRequired(user);
  await user.click(submitButton());

  expect(await screen.findByText(PHONE_ERROR)).toBeInTheDocument();
  expect(phoneInput()).toHaveAccessibleDescription(PHONE_ERROR);
  expect(phoneInput()).toBeInvalid();
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getByLabelText("Ваше имя")).toHaveValue("Мария");
});

test("captcha failure is shown as an alert and keeps values", async () => {
  stubApi(() => errorResponse(400, "captcha_failed", "Не удалось пройти проверку. Попробуйте ещё раз."));
  const user = userEvent.setup();
  renderForm();

  await fillRequired(user);
  await user.click(submitButton());

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Не удалось пройти проверку. Попробуйте ещё раз.",
  );
  expect(screen.getByLabelText("Имя ребёнка")).toHaveValue("Саша");
});

test("with captcha key the token is sent", async () => {
  const user = userEvent.setup();
  renderForm("client-key");

  expect(captchaProps).toHaveBeenCalledWith("client-key");
  await fillRequired(user);
  expect(fetchMock).not.toHaveBeenCalled();
  await user.click(submitButton());

  await screen.findByText(/Спасибо! Заявка отправлена/);
  expect(postBody()).toMatchObject({ captcha_token: "tok", parent_name: "Мария" });
});

test("without captcha key no widget is rendered and no token is sent", async () => {
  const user = userEvent.setup();
  renderForm(null);

  expect(screen.queryByTestId("captcha")).toBeNull();
  await fillRequired(user);
  await user.click(submitButton());

  await screen.findByText(/Спасибо! Заявка отправлена/);
  expect(postBody()).not.toHaveProperty("captcha_token");
});

test("consent label links to /privacy", () => {
  renderForm();

  expect(screen.getByRole("link", { name: "политикой" })).toHaveAttribute("href", "/privacy");
});

test("button is disabled while the request is in flight", async () => {
  let release: (response: Response) => void = () => {};
  fetchMock = vi.fn(
    (url: string, init?: RequestInit) =>
      new Promise<Response>((resolve) => {
        if (url === "/api/public/leads" && init?.method === "POST") release = resolve;
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const user = userEvent.setup();
  renderForm();

  await fillRequired(user);
  await user.click(submitButton());

  await waitFor(() => expect(screen.getByRole("button", { name: "Отправляем…" })).toBeDisabled());
  release(jsonResponse(201, { accepted: true }));
  await screen.findByText(/Спасибо! Заявка отправлена/);
});

const CAPTCHA_UNAVAILABLE =
  "Не удалось загрузить проверку «я не робот». Проверьте соединение и попробуйте ещё раз.";

async function startChallenge(user: ReturnType<typeof userEvent.setup>) {
  captcha.autoSolve = false;
  renderForm("client-key");
  await fillRequired(user);
  await user.click(submitButton());
  await waitFor(() => expect(screen.getByRole("button", { name: "Отправляем…" })).toBeDisabled());
}

function expectCaptchaUnavailable() {
  expect(screen.getByRole("alert")).toHaveTextContent(CAPTCHA_UNAVAILABLE);
  expect(submitButton()).toBeEnabled();
  expect(fetchMock).not.toHaveBeenCalled();
}

test.each([
  ["a network error", () => captcha.props?.onNetworkError?.()],
  [
    "a javascript error",
    () => captcha.props?.onJavascriptError?.({ filename: "c.js", message: "boom", col: 1, line: 1 }),
  ],
  ["an expired token", () => captcha.props?.onTokenExpired?.()],
])("%s during the challenge frees the form and sends nothing", async (_name, emit) => {
  await startChallenge(userEvent.setup());

  act(() => emit());

  expectCaptchaUnavailable();
});

test("closing the challenge frees the form and sends nothing", async () => {
  await startChallenge(userEvent.setup());

  act(() => captcha.props?.onChallengeHidden?.());

  expect(submitButton()).toBeEnabled();
  expect(screen.queryByRole("alert")).toBeNull();
  expect(fetchMock).not.toHaveBeenCalled();
});

test("a challenge that never answers is given up after 20 seconds", async () => {
  const user = userEvent.setup();
  captcha.autoSolve = false;
  renderForm("client-key");
  await fillRequired(user);

  // Под фейковыми таймерами user-event зависает в vitest (RTL ждёт jest), поэтому кликаем напрямую.
  vi.useFakeTimers();
  fireEvent.click(submitButton());
  await act(() => vi.advanceTimersByTimeAsync(0));
  expect(screen.getByRole("button", { name: "Отправляем…" })).toBeDisabled();

  await act(() => vi.advanceTimersByTimeAsync(19_999));
  expect(screen.getByRole("button", { name: "Отправляем…" })).toBeDisabled();
  expect(screen.queryByRole("alert")).toBeNull();

  await act(() => vi.advanceTimersByTimeAsync(1));
  expectCaptchaUnavailable();
});

test("the watchdog is cleared once the challenge ends", async () => {
  const user = userEvent.setup();
  captcha.autoSolve = false;
  renderForm("client-key");
  await fillRequired(user);

  // Под фейковыми таймерами user-event зависает в vitest (RTL ждёт jest), поэтому кликаем напрямую.
  vi.useFakeTimers();
  fireEvent.click(submitButton());
  await act(() => vi.advanceTimersByTimeAsync(0));
  act(() => captcha.props?.onChallengeHidden?.());

  await act(() => vi.advanceTimersByTimeAsync(60_000));

  expect(screen.queryByRole("alert")).toBeNull();
  expect(vi.getTimerCount()).toBe(0);
});
