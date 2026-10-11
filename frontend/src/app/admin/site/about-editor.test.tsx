import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const toastSuccess = vi.fn();
vi.mock("sonner", () => ({ toast: { success: (message: string) => toastSuccess(message) } }));

import type { AboutBlock } from "@/api/generated/model";

import { AboutEditor } from "./about-editor";

const about: AboutBlock = {
  text: "Привет",
  credentials: ["Диплом", "CELTA"],
  photo_media_id: null,
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

function stubApi() {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/admin/site-blocks/about" && init?.method === "PUT") {
      return jsonResponse(200, JSON.parse(String(init.body)));
    }
    if (url === "/api/admin/site-blocks") return jsonResponse(200, {});
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function lastPutBody(): AboutBlock {
  const call = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
  return JSON.parse(String(call?.[1].body));
}

function renderEditor(block: AboutBlock = about) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AboutEditor block={block} media={[]} />
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

test("preview renders markdown", async () => {
  const user = userEvent.setup();
  renderEditor();

  const text = screen.getByLabelText("Текст");
  await user.clear(text);
  await user.type(text, "**жирный**");
  await user.click(screen.getByRole("button", { name: "Предпросмотр" }));

  const strong = screen.getByText("жирный");
  expect(strong.tagName).toBe("STRONG");
  expect(screen.queryByLabelText("Текст")).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Предпросмотр" }));
  expect(screen.getByLabelText("Текст")).toHaveValue("**жирный**");
});

test("credentials can be added and removed", async () => {
  stubApi();
  const user = userEvent.setup();
  renderEditor();

  expect(screen.getAllByRole("textbox", { name: /^Пункт/ })).toHaveLength(2);

  await user.click(screen.getByRole("button", { name: "Добавить" }));
  const items = screen.getAllByRole("textbox", { name: /^Пункт/ });
  expect(items).toHaveLength(3);
  await user.type(items[2], "IELTS 8.0");

  await user.click(screen.getByRole("button", { name: "Удалить пункт 1" }));
  expect(screen.getAllByRole("textbox", { name: /^Пункт/ })).toHaveLength(2);

  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  await waitFor(() =>
    expect(toastSuccess).toHaveBeenCalledWith("Сохранено. Сайт обновится в течение минуты"),
  );
  expect(lastPutBody()).toEqual({
    text: "Привет",
    credentials: ["CELTA", "IELTS 8.0"],
    photo_media_id: null,
  });
});

test("blank credentials are dropped on save", async () => {
  stubApi();
  const user = userEvent.setup();
  renderEditor();

  await user.click(screen.getByRole("button", { name: "Добавить" }));
  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
  expect(lastPutBody().credentials).toEqual(["Диплом", "CELTA"]);
});

test("no more than 20 credentials", async () => {
  const user = userEvent.setup();
  renderEditor({ ...about, credentials: Array.from({ length: 20 }, (_, i) => `П${i}`) });

  expect(screen.getByRole("button", { name: "Добавить" })).toBeDisabled();

  await user.click(screen.getByRole("button", { name: "Удалить пункт 1" }));
  expect(screen.getByRole("button", { name: "Добавить" })).toBeEnabled();
});
