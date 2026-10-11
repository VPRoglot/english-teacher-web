import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { MediaOut } from "@/api/generated/model";

import { PhotoField } from "./photo-field";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const existing: MediaOut = {
  id: "m0",
  url: "/media/site/old.png",
  content_type: "image/png",
  size_bytes: 10,
  width: 10,
  height: 10,
};

let fetchMock: ReturnType<typeof vi.fn>;
const onChange = vi.fn();

function stubApi(response: Response) {
  fetchMock = vi.fn(async () => response);
  vi.stubGlobal("fetch", fetchMock);
}

const client = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

function field(value: string | null, media: MediaOut[]) {
  return <PhotoField label="Фото" value={value} media={media} onChange={onChange} />;
}

function renderField(value: string | null = null, media: MediaOut[] = []) {
  const queryClient = client();
  const view = render(<QueryClientProvider client={queryClient}>{field(value, media)}</QueryClientProvider>);
  return {
    rerenderWith: (nextValue: string | null, nextMedia: MediaOut[] = []) =>
      view.rerender(
        <QueryClientProvider client={queryClient}>{field(nextValue, nextMedia)}</QueryClientProvider>,
      ),
  };
}

beforeEach(() => {
  onChange.mockReset();
  document.cookie = "csrf_token=t";
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test("accepts only jpeg, png and webp", () => {
  renderField();
  expect(screen.getByLabelText("Фото")).toHaveAttribute(
    "accept",
    "image/jpeg,image/png,image/webp",
  );
});

test("shows preview of the current photo from media", () => {
  renderField("m0", [existing]);
  expect(screen.getByRole("img")).toHaveAttribute("src", "/media/site/old.png");
});

test("uploads selected file and shows preview", async () => {
  stubApi(
    jsonResponse(201, {
      id: "m1",
      url: "/media/site/x.png",
      content_type: "image/png",
      size_bytes: 3,
      width: 5,
      height: 5,
    }),
  );
  const user = userEvent.setup();
  const view = renderField();

  await user.upload(
    screen.getByLabelText("Фото"),
    new File(["abc"], "a.png", { type: "image/png" }),
  );

  await waitFor(() => expect(onChange).toHaveBeenCalledWith("m1"));
  const [url, init] = fetchMock.mock.calls[0];
  expect(url).toBe("/api/admin/media");
  expect(init.method).toBe("POST");
  expect(init.body).toBeInstanceOf(FormData);
  expect((init.body as FormData).get("file")).toBeInstanceOf(File);

  // Родитель применяет onChange и передаёт новый id; превью берётся из только что загруженного файла.
  view.rerenderWith("m1");
  expect(screen.getByRole("img")).toHaveAttribute("src", "/media/site/x.png");
});

test("rejects files over 5 MB without a request", async () => {
  stubApi(jsonResponse(201, {}));
  const user = userEvent.setup();
  renderField();

  const big = new File(["x"], "big.png", { type: "image/png" });
  Object.defineProperty(big, "size", { value: 5 * 1024 * 1024 + 1 });
  await user.upload(screen.getByLabelText("Фото"), big);

  expect(await screen.findByText("Файл больше 5 МБ")).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
  expect(onChange).not.toHaveBeenCalled();
});

test("shows API error from upload", async () => {
  stubApi(
    jsonResponse(415, {
      error: { code: "unsupported_media", message: "Неподдерживаемый формат", details: {} },
    }),
  );
  const user = userEvent.setup();
  renderField();

  await user.upload(
    screen.getByLabelText("Фото"),
    new File(["abc"], "a.png", { type: "image/png" }),
  );

  expect(await screen.findByText("Неподдерживаемый формат")).toBeInTheDocument();
  expect(onChange).not.toHaveBeenCalled();
});

test("remove clears the photo", async () => {
  const user = userEvent.setup();
  renderField("m0", [existing]);

  await user.click(screen.getByRole("button", { name: "Убрать фото" }));

  expect(onChange).toHaveBeenCalledWith(null);
});

test("remove button is hidden when there is no photo", () => {
  renderField();
  expect(screen.queryByRole("button", { name: "Убрать фото" })).not.toBeInTheDocument();
});
