import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const toastSuccess = vi.fn();
vi.mock("sonner", () => ({ toast: { success: (message: string) => toastSuccess(message) } }));

import type { FaqBlock } from "@/api/generated/model";

import { FaqEditor } from "./faq-editor";

const faq: FaqBlock = { items: [{ question: "Сколько длится урок?", answer: "Час" }] };

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

function stubApi() {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/admin/site-blocks/faq" && init?.method === "PUT") {
      return jsonResponse(200, JSON.parse(String(init.body)));
    }
    if (url === "/api/admin/site-blocks") return jsonResponse(200, {});
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function lastPutBody(): FaqBlock {
  const call = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
  return JSON.parse(String(call?.[1].body));
}

function renderEditor(block: FaqBlock = faq) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <FaqEditor block={block} />
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

test("saves questions in order", async () => {
  stubApi();
  const user = userEvent.setup();
  renderEditor();

  await user.click(screen.getByRole("button", { name: "Добавить вопрос" }));
  const added = screen.getByRole("group", { name: "Вопрос 2" });
  await user.type(within(added).getByLabelText("Вопрос"), "Есть ли пробный урок?");
  await user.type(within(added).getByLabelText("Ответ"), "Да, бесплатно");
  await user.click(screen.getByRole("button", { name: "Переместить вопрос 2 выше" }));
  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  await waitFor(() =>
    expect(toastSuccess).toHaveBeenCalledWith("Сохранено. Сайт обновится в течение минуты"),
  );
  expect(lastPutBody().items).toEqual([
    { question: "Есть ли пробный урок?", answer: "Да, бесплатно" },
    { question: "Сколько длится урок?", answer: "Час" },
  ]);
});

test("add button is disabled at 30 questions", () => {
  renderEditor({ items: Array.from({ length: 30 }, () => faq.items[0]) });

  expect(screen.getByRole("button", { name: "Добавить вопрос" })).toBeDisabled();
});

test("a blank question is reported on its own row", async () => {
  stubApi();
  const user = userEvent.setup();
  renderEditor();

  await user.click(screen.getByRole("button", { name: "Добавить вопрос" }));
  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  const row2 = screen.getByRole("group", { name: "Вопрос 2" });
  expect(await within(row2).findAllByText("Заполните поле")).toHaveLength(2);
  expect(
    within(screen.getByRole("group", { name: "Вопрос 1" })).queryByText("Заполните поле"),
  ).toBeNull();
  expect(fetchMock).not.toHaveBeenCalled();
});
