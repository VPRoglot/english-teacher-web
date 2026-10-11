import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const toastSuccess = vi.fn();
vi.mock("sonner", () => ({ toast: { success: (message: string) => toastSuccess(message) } }));

import type { ServiceItem, ServicesBlock } from "@/api/generated/model";

import { ServicesEditor } from "./services-editor";

const first: ServiceItem = {
  title: "Разговорный клуб",
  description: "Практика речи",
  duration_min: 45,
  price_rub: 1500,
  format: "Группа",
};
const second: ServiceItem = {
  title: "Подготовка к ОГЭ",
  description: "",
  duration_min: 90,
  price_rub: 3000,
  format: "Индивидуально",
};
const services: ServicesBlock = { items: [first, second] };

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

function stubApi() {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/admin/site-blocks/services" && init?.method === "PUT") {
      return jsonResponse(200, JSON.parse(String(init.body)));
    }
    if (url === "/api/admin/site-blocks") return jsonResponse(200, {});
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function lastPutBody(): ServicesBlock {
  const call = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
  return JSON.parse(String(call?.[1].body));
}

function renderEditor(block: ServicesBlock = services) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ServicesEditor block={block} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  toastSuccess.mockReset();
  document.cookie = "csrf_token=t";
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test("adds, edits and saves a service", async () => {
  stubApi();
  const user = userEvent.setup();
  renderEditor({ items: [first] });

  await user.click(screen.getByRole("button", { name: "Добавить услугу" }));
  const item = screen.getByRole("group", { name: "Услуга 2" });
  await user.type(within(item).getByLabelText("Название"), "Пробный урок");
  await user.type(within(item).getByLabelText("Длительность, мин"), "60");
  await user.type(within(item).getByLabelText("Цена, ₽"), "2000");
  await user.type(within(item).getByLabelText("Формат"), "Онлайн");
  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  await waitFor(() =>
    expect(toastSuccess).toHaveBeenCalledWith("Сохранено. Сайт обновится в течение минуты"),
  );
  expect(lastPutBody().items).toEqual([
    first,
    { title: "Пробный урок", description: "", duration_min: 60, price_rub: 2000, format: "Онлайн" },
  ]);
});

test("moves and removes items", async () => {
  stubApi();
  const user = userEvent.setup();
  renderEditor();

  expect(screen.getByRole("button", { name: "Переместить услугу 1 выше" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Переместить услугу 2 ниже" })).toBeDisabled();

  await user.click(screen.getByRole("button", { name: "Переместить услугу 1 ниже" }));
  expect(
    screen.getAllByLabelText("Название").map((input) => (input as HTMLInputElement).value),
  ).toEqual([second.title, first.title]);
  await user.click(screen.getByRole("button", { name: "Сохранить" }));
  await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
  expect(lastPutBody().items).toEqual([second, first]);

  await user.click(screen.getByRole("button", { name: "Удалить услугу 1" }));
  expect(screen.getAllByLabelText("Название")).toHaveLength(1);
  expect(screen.getByLabelText("Название")).toHaveValue(first.title);
});

test("add button is disabled at 20 items", async () => {
  const user = userEvent.setup();
  renderEditor({ items: Array.from({ length: 20 }, () => first) });

  expect(screen.getByRole("button", { name: "Добавить услугу" })).toBeDisabled();

  await user.click(screen.getByRole("button", { name: "Удалить услугу 1" }));
  expect(screen.getByRole("button", { name: "Добавить услугу" })).toBeEnabled();
});

test("shows field errors under the row they belong to", async () => {
  stubApi();
  const user = userEvent.setup();
  renderEditor();

  const row2 = screen.getByRole("group", { name: "Услуга 2" });
  await user.clear(within(row2).getByLabelText("Название"));
  await user.clear(within(row2).getByLabelText("Цена, ₽"));
  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  expect(await within(row2).findByText("Заполните поле")).toBeInTheDocument();
  expect(within(row2).getByText("Введите число")).toBeInTheDocument();
  expect(
    within(screen.getByRole("group", { name: "Услуга 1" })).queryByText("Заполните поле"),
  ).toBeNull();
  expect(fetchMock).not.toHaveBeenCalled();
});
