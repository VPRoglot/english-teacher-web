import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { SiteEditor } from "./site-editor";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const blocks = {
  hero: {
    name: "Анна Иванова",
    title: "Английский для детей",
    subtitle: "Занятия онлайн",
    cta_text: "Записаться",
    photo_media_id: "m1",
  },
  about: { text: "Привет", credentials: ["Диплом"], photo_media_id: null },
  contacts: { email: null, phone: null, telegram: "@anna", whatsapp: null, working_hours_text: null },
  services: { items: [] },
  reviews: { items: [] },
  faq: { items: [] },
  media: [
    {
      id: "m1",
      url: "/media/site/hero.png",
      content_type: "image/png",
      size_bytes: 10,
      width: 10,
      height: 10,
    },
  ],
};

function renderEditor() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SiteEditor />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test("shows a skeleton, then editors in landing order with the site link", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(200, blocks)));
  renderEditor();

  expect(screen.getByRole("status", { name: "Загрузка" })).toBeInTheDocument();

  const hero = await screen.findByText("Главный экран");
  const about = screen.getByText("Обо мне");
  const contacts = screen.getByText("Контакты");
  expect(hero.compareDocumentPosition(about) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(about.compareDocumentPosition(contacts) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

  expect(screen.getByLabelText("Заголовок")).toHaveValue("Английский для детей");
  expect(screen.getByRole("img")).toHaveAttribute("src", "/media/site/hero.png");

  const link = screen.getByRole("link", { name: "Открыть сайт" });
  expect(link).toHaveAttribute("href", "/");
  expect(link).toHaveAttribute("target", "_blank");
  expect(link).toHaveAttribute("rel", "noopener noreferrer");
});

test("shows the API error", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      jsonResponse(500, { error: { code: "internal_error", message: "Сбой сервера", details: {} } }),
    ),
  );
  renderEditor();

  expect(await screen.findByRole("alert")).toHaveTextContent("Сбой сервера");
});
