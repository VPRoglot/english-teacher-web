import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const toastSuccess = vi.fn();
vi.mock("sonner", () => ({ toast: { success: (message: string) => toastSuccess(message) } }));

import type { MediaOut, ReviewsBlock } from "@/api/generated/model";

import { ReviewsEditor } from "./reviews-editor";

const media: MediaOut[] = [
  {
    id: "7a1f0c52-0d3c-4f7e-9d0f-1d1d5b9d4b11",
    url: "/media/site/anna.png",
    content_type: "image/png",
    size_bytes: 10,
    width: 10,
    height: 10,
  },
];

const reviews: ReviewsBlock = {
  items: [
    { author: "Анна", text: "Отлично", child_age: 10, photo_media_id: media[0].id },
    { author: "Борис", text: "Хорошо", child_age: null, photo_media_id: null },
  ],
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

function stubApi(putResponse?: Response) {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/admin/site-blocks/reviews" && init?.method === "PUT") {
      return putResponse ?? jsonResponse(200, JSON.parse(String(init.body)));
    }
    if (url === "/api/admin/site-blocks") return jsonResponse(200, {});
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function lastPutBody(): ReviewsBlock {
  const call = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
  return JSON.parse(String(call?.[1].body));
}

function renderEditor(block: ReviewsBlock = reviews) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ReviewsEditor block={block} media={media} />
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

test("empty child age is sent as null", async () => {
  stubApi();
  const user = userEvent.setup();
  renderEditor();

  const age = within(screen.getByRole("group", { name: "Отзыв 1" })).getByLabelText(
    "Возраст ребёнка",
  );
  expect(age).toHaveValue(10);
  await user.clear(age);
  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  await waitFor(() =>
    expect(toastSuccess).toHaveBeenCalledWith("Сохранено. Сайт обновится в течение минуты"),
  );
  expect(lastPutBody().items).toEqual([
    { author: "Анна", text: "Отлично", child_age: null, photo_media_id: media[0].id },
    { author: "Борис", text: "Хорошо", child_age: null, photo_media_id: null },
  ]);
});

test("each review has its own photo and it can be removed", async () => {
  stubApi();
  const user = userEvent.setup();
  renderEditor();

  const row1 = screen.getByRole("group", { name: "Отзыв 1" });
  const row2 = screen.getByRole("group", { name: "Отзыв 2" });
  expect(within(row1).getByRole("img")).toHaveAttribute("src", "/media/site/anna.png");
  expect(within(row2).queryByRole("img")).toBeNull();

  await user.click(within(row1).getByRole("button", { name: "Убрать фото" }));
  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
  expect(lastPutBody().items.map((item) => item.photo_media_id)).toEqual([null, null]);
});

test("a photo follows its review when items are moved", async () => {
  stubApi();
  const user = userEvent.setup();
  renderEditor();

  await user.click(screen.getByRole("button", { name: "Переместить отзыв 1 ниже" }));
  expect(
    within(screen.getByRole("group", { name: "Отзыв 2" })).getByRole("img"),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
  expect(lastPutBody().items.map((item) => [item.author, item.photo_media_id])).toEqual([
    ["Борис", null],
    ["Анна", media[0].id],
  ]);
});

test("age above 18 is reported on its row", async () => {
  stubApi();
  const user = userEvent.setup();
  renderEditor();

  const row2 = screen.getByRole("group", { name: "Отзыв 2" });
  await user.type(within(row2).getByLabelText("Возраст ребёнка"), "25");
  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  expect(await within(row2).findByText("Не больше 18")).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
});

test("add button is disabled at 30 reviews", () => {
  renderEditor({ items: Array.from({ length: 30 }, () => reviews.items[1]) });

  expect(screen.getByRole("button", { name: "Добавить отзыв" })).toBeDisabled();
});

test("unknown photo error is shown on the form", async () => {
  stubApi(
    jsonResponse(422, {
      error: {
        code: "validation_error",
        message: "Фото не найдено — загрузите его заново",
        details: {
          fields: [
            {
              loc: ["body", "items", 1, "photo_media_id"],
              message: "Фото не найдено — загрузите его заново",
            },
          ],
        },
      },
    }),
  );
  const user = userEvent.setup();
  renderEditor();

  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Фото не найдено — загрузите его заново",
  );
  expect(toastSuccess).not.toHaveBeenCalled();
});
