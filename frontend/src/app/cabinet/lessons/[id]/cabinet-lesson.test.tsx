import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { LessonForFamilyDetail } from "@/api/generated/model";

let search = "";
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "l1" }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/cabinet/lessons/l1",
  useSearchParams: () => new URLSearchParams(search),
}));

import { CabinetLesson } from "./cabinet-lesson";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function makeLesson(overrides: Partial<LessonForFamilyDetail> = {}): LessonForFamilyDetail {
  return {
    id: "l1",
    child_id: "c1",
    child_name: "Петя",
    duration_min: 60,
    has_shared_note: true,
    join_url: "https://meet.example.com/petya",
    shared_note: "**Домашка:** выучить слова",
    starts_at: "2026-10-13T15:00:00Z", // вт, 18:00 по Москве
    status: "scheduled",
    ...overrides,
  };
}

const KIDS = [
  { id: "c1", full_name: "Петя" },
  { id: "c2", full_name: "Маша" },
];

let lessonResponse: () => Response;

function stubApi() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url === "/api/auth/me") {
        return jsonResponse(200, {
          id: "u1",
          role: "parent",
          display_name: "Мария",
          email: null,
          username: null,
          family: null,
          children: KIDS,
        });
      }
      if (url === "/api/me/schedule-settings") {
        return jsonResponse(200, { timezone: "Europe/Moscow", cancel_policy_hours: 24 });
      }
      if (url === "/api/me/lessons/l1") return lessonResponse();
      throw new Error(`unexpected fetch ${url}`);
    }),
  );
}

function renderLesson() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CabinetLesson />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  search = "";
  lessonResponse = () => jsonResponse(200, makeLesson());
  document.cookie = "csrf_token=t";
  stubApi();
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test("shows when, child, status and join link", async () => {
  renderLesson();
  expect(await screen.findByRole("heading", { name: "Петя" })).toBeInTheDocument();
  expect(screen.getByText(/18:00–19:00/)).toBeInTheDocument();
  expect(screen.getByText("Запланировано")).toBeInTheDocument();
  const join = screen.getByRole("link", { name: "Подключиться" });
  expect(join).toHaveAttribute("href", "https://meet.example.com/petya");
  expect(join).toHaveAttribute("target", "_blank");
  expect(join).toHaveAttribute("rel", "noopener noreferrer");
});

test("join button is disabled without a link", async () => {
  lessonResponse = () => jsonResponse(200, makeLesson({ join_url: null }));
  renderLesson();
  expect(await screen.findByText("Ссылку пришлёт репетитор")).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Подключиться" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Подключиться" })).toBeDisabled();
});

test("renders shared note as markdown", async () => {
  renderLesson();
  expect(await screen.findByText("Заметка репетитора")).toBeInTheDocument();
  const bold = await screen.findByText("Домашка:");
  expect(bold.tagName).toBe("STRONG");
  expect(screen.getByText(/выучить слова/)).toBeInTheDocument();
});

test("does not render raw html from the note", async () => {
  lessonResponse = () =>
    jsonResponse(200, makeLesson({ shared_note: 'текст <script>alert(1)</script><b>жирный</b>' }));
  const view = renderLesson();
  await screen.findByText("Заметка репетитора");
  await screen.findByText(/текст/);
  expect(view.container.querySelector("script")).toBeNull();
  expect(view.container.querySelector("b")).toBeNull();
});

test("says there is no note yet", async () => {
  lessonResponse = () => jsonResponse(200, makeLesson({ shared_note: null, has_shared_note: false }));
  renderLesson();
  expect(await screen.findByText("Заметки пока нет")).toBeInTheDocument();
});

test("back link to the calendar keeps the selected child", async () => {
  search = "child=c2";
  renderLesson();
  expect(await screen.findByRole("link", { name: "← К календарю" })).toHaveAttribute(
    "href",
    "/cabinet/calendar?child=c2",
  );
});

test("back link without a selected child has no query", async () => {
  renderLesson();
  expect(await screen.findByRole("link", { name: "← К календарю" })).toHaveAttribute(
    "href",
    "/cabinet/calendar",
  );
});

test("not found message on 404", async () => {
  lessonResponse = () =>
    jsonResponse(404, { error: { code: "lesson_not_found", message: "Not found", details: {} } });
  renderLesson();
  expect(await screen.findByText("Занятие не найдено")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "← К календарю" })).toBeInTheDocument();
});
