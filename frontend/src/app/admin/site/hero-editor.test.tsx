import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const toastSuccess = vi.fn();
vi.mock("sonner", () => ({ toast: { success: (message: string) => toastSuccess(message) } }));

import type { HeroBlock } from "@/api/generated/model";

import { HeroEditor } from "./hero-editor";

const hero: HeroBlock = {
  name: "Анна Иванова",
  title: "Английский для детей",
  subtitle: "Занятия онлайн",
  cta_text: "Записаться",
  photo_media_id: null,
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

function stubApi(respond: (init: RequestInit) => Response) {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/admin/site-blocks/hero" && init?.method === "PUT") return respond(init);
    if (url === "/api/admin/site-blocks" && init?.method === "GET") return jsonResponse(200, {});
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function putCalls() {
  return fetchMock.mock.calls.filter(([, init]) => init?.method === "PUT");
}

function renderEditor() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <HeroEditor block={hero} media={[]} />
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

test("submits edited hero and reports success", async () => {
  stubApi((init) => jsonResponse(200, JSON.parse(String(init.body))));
  const user = userEvent.setup();
  renderEditor();

  const title = screen.getByLabelText("Заголовок");
  expect(title).toHaveValue("Английский для детей");
  await user.clear(title);
  await user.type(title, "Новый заголовок");
  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  await waitFor(() =>
    expect(toastSuccess).toHaveBeenCalledWith("Сохранено. Сайт обновится в течение минуты"),
  );
  expect(putCalls()).toHaveLength(1);
  expect(JSON.parse(String(putCalls()[0][1].body))).toEqual({
    name: "Анна Иванова",
    title: "Новый заголовок",
    subtitle: "Занятия онлайн",
    cta_text: "Записаться",
    photo_media_id: null,
  });
});

test("empty required field is rejected on the client without a request", async () => {
  stubApi((init) => jsonResponse(200, JSON.parse(String(init.body))));
  const user = userEvent.setup();
  renderEditor();

  await user.clear(screen.getByLabelText("Заголовок"));
  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  expect(await screen.findByText("Заполните поле")).toBeInTheDocument();
  expect(putCalls()).toHaveLength(0);
});

test("server field errors land on fields", async () => {
  stubApi(() =>
    jsonResponse(422, {
      error: {
        code: "validation_error",
        message: "Ошибка валидации",
        details: { fields: [{ loc: ["body", "title"], message: "Слишком длинно" }] },
      },
    }),
  );
  const user = userEvent.setup();
  renderEditor();

  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  expect(await screen.findByText("Слишком длинно")).toBeInTheDocument();
  expect(screen.getByLabelText("Заголовок")).toHaveAttribute("aria-invalid", "true");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(toastSuccess).not.toHaveBeenCalled();
});

test("other API errors are shown in an alert", async () => {
  stubApi(() =>
    jsonResponse(500, { error: { code: "internal_error", message: "Сбой сервера", details: {} } }),
  );
  const user = userEvent.setup();
  renderEditor();

  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Сбой сервера");
});

test("save button is disabled while the request is in flight", async () => {
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === "PUT") {
      await gate;
      return jsonResponse(200, JSON.parse(String(init.body)));
    }
    return jsonResponse(200, {});
  });
  vi.stubGlobal("fetch", fetchMock);
  const user = userEvent.setup();
  renderEditor();

  await user.click(screen.getByRole("button", { name: "Сохранить" }));
  await waitFor(() => expect(screen.getByRole("button", { name: /Сохраняем/ })).toBeDisabled());
  release();
  await waitFor(() => expect(screen.getByRole("button", { name: "Сохранить" })).toBeEnabled());
});
