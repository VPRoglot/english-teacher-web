import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { LessonForFamily } from "@/api/generated/model";

let search = "";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/cabinet",
  useSearchParams: () => new URLSearchParams(search),
}));

import { Home } from "./home";

const NOW = new Date("2026-10-12T09:00:00Z");
const DAY_MS = 86_400_000;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function lesson(overrides: Partial<LessonForFamily> = {}): LessonForFamily {
  return {
    id: "l1",
    child_id: "c1",
    child_name: "Петя",
    duration_min: 60,
    has_shared_note: false,
    join_url: "https://meet.example.com/petya",
    starts_at: "2026-10-13T15:00:00Z", // вт, 18:00 по Москве
    status: "scheduled",
    ...overrides,
  };
}

const KIDS = [
  { id: "c1", full_name: "Петя" },
  { id: "c2", full_name: "Маша" },
];

let role: "parent" | "child";
let upcoming: LessonForFamily[];
let past: LessonForFamily[];
let fetchMock: ReturnType<typeof vi.fn>;

function stubApi() {
  fetchMock = vi.fn(async (url: string) => {
    if (url === "/api/auth/me") {
      return jsonResponse(200, {
        id: "u1",
        role,
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
    if (url.startsWith("/api/me/lessons?")) {
      // Окно заметок заканчивается «сейчас», окно предстоящих — через 28 дней.
      const to = new Date(new URL(url, "http://localhost").searchParams.get("to") ?? "");
      return jsonResponse(200, to.getTime() === NOW.getTime() ? past : upcoming);
    }
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function lessonRequests(): URL[] {
  return fetchMock.mock.calls
    .map(([url]) => String(url))
    .filter((url) => url.startsWith("/api/me/lessons?"))
    .map((url) => new URL(url, "http://localhost"));
}

function renderHome() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Home />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
  search = "";
  role = "parent";
  upcoming = [lesson()];
  past = [];
  document.cookie = "csrf_token=t";
  stubApi();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

async function cardOf(title: string) {
  const heading = await screen.findByText(title);
  return within(heading.closest('[data-slot="card"]') as HTMLElement);
}

test("nearest lesson card with join button", async () => {
  renderHome();
  const card = await cardOf("Ближайшее занятие");
  expect(await card.findByText(/18:00–19:00/)).toBeInTheDocument();
  expect(card.getByText(/Петя/)).toBeInTheDocument();
  expect(card.getByText("Запланировано")).toBeInTheDocument();
  const join = card.getByRole("link", { name: "Подключиться" });
  expect(join).toHaveAttribute("href", "https://meet.example.com/petya");
  expect(join).toHaveAttribute("target", "_blank");
  expect(join).toHaveAttribute("rel", "noopener noreferrer");
});

test("join button disabled without link", async () => {
  upcoming = [lesson({ join_url: null })];
  renderHome();
  const card = await cardOf("Ближайшее занятие");
  expect(await card.findByText("Ссылку пришлёт репетитор")).toBeInTheDocument();
  expect(card.queryByRole("link", { name: "Подключиться" })).not.toBeInTheDocument();
  expect(card.getByRole("button", { name: "Подключиться" })).toBeDisabled();
});

test("nearest lesson is the first scheduled one", async () => {
  upcoming = [
    lesson({ id: "x", status: "cancelled", child_name: "Отменённый" }),
    lesson({ id: "y", starts_at: "2026-10-14T15:00:00Z", child_name: "Следующий" }),
  ];
  renderHome();
  const card = await cardOf("Ближайшее занятие");
  expect(await card.findByText(/Следующий/)).toBeInTheDocument();
  expect(card.queryByText(/Отменённый/)).not.toBeInTheDocument();
});

test("no lessons: empty texts", async () => {
  upcoming = [];
  renderHome();
  expect(await screen.findByText("Ближайших занятий нет")).toBeInTheDocument();
  expect(await screen.findByText("Заметок пока нет")).toBeInTheDocument();
});

test("upcoming lists up to five lessons after the nearest, each a link", async () => {
  upcoming = Array.from({ length: 8 }, (_, index) =>
    lesson({ id: `l${index + 1}`, starts_at: `2026-10-${13 + index}T15:00:00Z` }),
  );
  renderHome();
  const card = await cardOf("Предстоящие");
  const links = await card.findAllByRole("link");
  expect(links.map((link) => link.getAttribute("href"))).toEqual([
    "/cabinet/lessons/l2",
    "/cabinet/lessons/l3",
    "/cabinet/lessons/l4",
    "/cabinet/lessons/l5",
    "/cabinet/lessons/l6",
  ]);
});

test("recent notes list only lessons with shared notes", async () => {
  past = [
    lesson({ id: "n1", starts_at: "2026-10-05T15:00:00Z", has_shared_note: true }),
    lesson({ id: "n2", starts_at: "2026-10-06T15:00:00Z", has_shared_note: false }),
    lesson({
      id: "n3",
      starts_at: "2026-10-07T15:00:00Z",
      has_shared_note: true,
      child_name: "Маша",
    }),
    lesson({ id: "n4", starts_at: "2026-10-08T15:00:00Z", has_shared_note: true }),
    lesson({ id: "n5", starts_at: "2026-10-09T15:00:00Z", has_shared_note: true }),
  ];
  renderHome();
  const card = await cardOf("Последние заметки");
  const links = await card.findAllByRole("link");
  expect(links.map((link) => [link.textContent, link.getAttribute("href")])).toEqual([
    ["09.10.2026 · Петя — открыть заметку", "/cabinet/lessons/n5"],
    ["08.10.2026 · Петя — открыть заметку", "/cabinet/lessons/n4"],
    ["07.10.2026 · Маша — открыть заметку", "/cabinet/lessons/n3"],
  ]);
});

test("recent notes are ordered newest first whatever the API order", async () => {
  past = [
    lesson({ id: "n4", starts_at: "2026-10-08T15:00:00Z", has_shared_note: true }),
    lesson({ id: "n9", starts_at: "2026-10-09T15:00:00Z", has_shared_note: true }),
    lesson({ id: "n1", starts_at: "2026-10-01T15:00:00Z", has_shared_note: true }),
    lesson({ id: "n7", starts_at: "2026-10-07T15:00:00Z", has_shared_note: true }),
  ];
  renderHome();
  const card = await cardOf("Последние заметки");
  const links = await card.findAllByRole("link");
  expect(links.map((link) => link.getAttribute("href"))).toEqual([
    "/cabinet/lessons/n9",
    "/cabinet/lessons/n4",
    "/cabinet/lessons/n7",
  ]);
});

test("nearest and upcoming are right for unsorted API data", async () => {
  upcoming = [
    lesson({ id: "c", starts_at: "2026-10-15T15:00:00Z" }),
    lesson({ id: "a", starts_at: "2026-10-13T15:00:00Z" }),
    lesson({ id: "b", starts_at: "2026-10-14T15:00:00Z" }),
  ];
  renderHome();
  const nearest = await cardOf("Ближайшее занятие");
  expect((await nearest.findByRole("link", { name: /18:00/ })).getAttribute("href")).toBe(
    "/cabinet/lessons/a",
  );
  const card = await cardOf("Предстоящие");
  const links = await card.findAllByRole("link");
  expect(links.map((link) => link.getAttribute("href"))).toEqual([
    "/cabinet/lessons/b",
    "/cabinet/lessons/c",
  ]);
});

test("a lesson in progress stays the nearest one with the join button", async () => {
  upcoming = [
    lesson({
      id: "live",
      starts_at: new Date(NOW.getTime() - 30 * 60_000).toISOString(),
      duration_min: 60,
      child_name: "Идёт сейчас",
    }),
    lesson({ id: "later", starts_at: "2026-10-14T15:00:00Z" }),
  ];
  renderHome();
  const card = await cardOf("Ближайшее занятие");
  expect(await card.findByText(/Идёт сейчас/)).toBeInTheDocument();
  expect(card.getByRole("link", { name: "Подключиться" })).toHaveAttribute(
    "href",
    "https://meet.example.com/petya",
  );
  const following = await cardOf("Предстоящие");
  expect(
    (await following.findAllByRole("link")).map((link) => link.getAttribute("href")),
  ).toEqual(["/cabinet/lessons/later"]);
});

test("a lesson that has already ended is not shown as upcoming", async () => {
  upcoming = [
    lesson({
      id: "over",
      starts_at: new Date(NOW.getTime() - 90 * 60_000).toISOString(),
      duration_min: 60,
      child_name: "Закончилось",
    }),
  ];
  renderHome();
  expect(await screen.findByText("Ближайших занятий нет")).toBeInTheDocument();
  expect(screen.queryByText(/Закончилось/)).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Подключиться" })).not.toBeInTheDocument();
});

test("the upcoming window follows the clock instead of freezing at mount", async () => {
  vi.useRealTimers();
  vi.useFakeTimers({
    toFake: ["Date", "setTimeout", "clearTimeout"],
    shouldAdvanceTime: true,
  });
  vi.setSystemTime(NOW);
  upcoming = [
    lesson({
      id: "short",
      starts_at: new Date(NOW.getTime() - 30 * 60_000).toISOString(),
      duration_min: 45,
      child_name: "Скоро закончится",
    }),
  ];
  renderHome();
  expect(await screen.findByText(/Скоро закончится/)).toBeInTheDocument();

  // Через 20 минут занятие (45 минут с -30) закончилось: страница сама это замечает.
  await act(async () => {
    await vi.advanceTimersByTimeAsync(20 * 60_000);
  });

  await waitFor(() => expect(screen.queryByText(/Скоро закончится/)).not.toBeInTheDocument());
  expect(await screen.findByText("Ближайших занятий нет")).toBeInTheDocument();
  const froms = lessonRequests().map((url) => url.searchParams.get("from"));
  const laterFrom = new Date(NOW.getTime() + 20 * 60_000 - 240 * 60_000).toISOString();
  expect(froms.some((from) => from !== null && new Date(from) >= new Date(laterFrom))).toBe(true);
});

test("requests cover the in-progress window, the next 28 days and the last 56 days", async () => {
  renderHome();
  await waitFor(() => expect(lessonRequests()).toHaveLength(2));
  const windows = lessonRequests().map((url) => [
    url.searchParams.get("from"),
    url.searchParams.get("to"),
  ]);
  // Начало окна — «сейчас» минус максимальная длительность занятия (240 минут).
  expect(windows).toContainEqual([
    new Date(NOW.getTime() - 240 * 60_000).toISOString(),
    new Date(NOW.getTime() + 28 * DAY_MS).toISOString(),
  ]);
  expect(windows).toContainEqual([
    new Date(NOW.getTime() - 56 * DAY_MS).toISOString(),
    NOW.toISOString(),
  ]);
  expect(lessonRequests().every((url) => !url.searchParams.has("child_id"))).toBe(true);
});

test("requests use selected child", async () => {
  search = "child=c2";
  renderHome();
  await waitFor(() => expect(lessonRequests()).toHaveLength(2));
  expect(lessonRequests().map((url) => url.searchParams.get("child_id"))).toEqual(["c2", "c2"]);
});

test("lesson links keep the selected child", async () => {
  search = "child=c2";
  upcoming = [lesson({ id: "a" }), lesson({ id: "b", starts_at: "2026-10-14T15:00:00Z" })];
  past = [lesson({ id: "n1", starts_at: "2026-10-05T15:00:00Z", has_shared_note: true })];
  renderHome();
  const upcomingCard = await cardOf("Предстоящие");
  expect((await upcomingCard.findByRole("link")).getAttribute("href")).toBe(
    "/cabinet/lessons/b?child=c2",
  );
  const notes = await cardOf("Последние заметки");
  expect((await notes.findByRole("link")).getAttribute("href")).toBe("/cabinet/lessons/n1?child=c2");
  const nearest = await cardOf("Ближайшее занятие");
  expect((await nearest.findByRole("link", { name: /18:00/ })).getAttribute("href")).toBe(
    "/cabinet/lessons/a?child=c2",
  );
});

test("parent keeps the children card", async () => {
  renderHome();
  expect(await screen.findByText("Дети")).toBeInTheDocument();
  expect(screen.getByText("Маша")).toBeInTheDocument();
});

test("a child does not see the children card", async () => {
  role = "child";
  renderHome();
  await screen.findByText("Ближайшее занятие");
  expect(screen.queryByText("Дети")).not.toBeInTheDocument();
});
