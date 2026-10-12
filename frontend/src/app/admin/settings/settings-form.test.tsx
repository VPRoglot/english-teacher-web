import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const toastSuccess = vi.fn();
vi.mock("sonner", () => ({ toast: { success: (message: string) => toastSuccess(message) } }));

import { SettingsForm } from "./settings-form";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

let fetchMock: ReturnType<typeof vi.fn>;
let putResponse: () => Response;
let settings: { timezone: string; cancel_policy_hours: number };

function stubApi() {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/admin/settings" && init?.method === "GET") return jsonResponse(200, settings);
    if (url === "/api/admin/settings" && init?.method === "PUT") return putResponse();
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function calls(method: string): unknown[][] {
  return fetchMock.mock.calls.filter(
    ([url, init]) => url === "/api/admin/settings" && init?.method === method,
  );
}

let client: QueryClient;

function renderForm() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SettingsForm />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  toastSuccess.mockReset();
  settings = { timezone: "Europe/Moscow", cancel_policy_hours: 24 };
  putResponse = () => jsonResponse(200, { timezone: "Asia/Yekaterinburg", cancel_policy_hours: 12 });
  document.cookie = "csrf_token=t";
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test("loads and saves settings", async () => {
  stubApi();
  const user = userEvent.setup();
  renderForm();

  const zone = await screen.findByLabelText("Часовой пояс");
  expect(zone).toHaveValue("Europe/Moscow");
  expect(screen.getByLabelText("Порог поздней отмены, часов")).toHaveValue(24);
  expect(screen.getByText("Смена пояса сохраняет местное время регулярных занятий")).toBeInTheDocument();

  await user.selectOptions(zone, "Asia/Yekaterinburg");
  const hours = screen.getByLabelText("Порог поздней отмены, часов");
  await user.clear(hours);
  await user.type(hours, "12");
  const invalidate = vi.spyOn(client, "invalidateQueries");
  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Настройки сохранены"));
  expect(JSON.parse(String((calls("PUT")[0][1] as RequestInit).body))).toEqual({
    timezone: "Asia/Yekaterinburg",
    cancel_policy_hours: 12,
  });
  const keys = invalidate.mock.calls.map(([filters]) => (filters as { queryKey?: unknown }).queryKey);
  expect(keys).toContainEqual(["/api/admin/settings"]);
  // Lessons lists are keyed by a prefix; they are invalidated with a predicate over the key.
  const predicates = invalidate.mock.calls
    .map(([filters]) => (filters as { predicate?: (q: { queryKey: unknown[] }) => boolean }).predicate)
    .filter((predicate) => predicate !== undefined);
  expect(predicates.some((p) => p({ queryKey: ["/api/admin/lessons", { from: "x" }] }))).toBe(true);
  expect(predicates.some((p) => p({ queryKey: ["/api/admin/lessons/abc"] }))).toBe(true);
  expect(predicates.some((p) => p({ queryKey: ["/api/admin/series", { child_id: "c1" }] }))).toBe(true);
  expect(
    predicates.some((p) => p({ queryKey: ["/api/admin/leads/lead-1/trial-lessons"] })),
  ).toBe(true);
  expect(predicates.some((p) => p({ queryKey: ["/api/admin/leads"] }))).toBe(false);
});

test("Europe/Moscow is the first option", async () => {
  stubApi();
  renderForm();
  const zone = await screen.findByLabelText("Часовой пояс");
  const options = Array.from(zone.querySelectorAll("option")).map((option) => option.value);
  expect(options[0]).toBe("Europe/Moscow");
  expect(options).toContain("Asia/Yekaterinburg");
  expect(options.filter((value) => value === "Europe/Moscow")).toHaveLength(1);
});

test("a stored zone missing from the browser list is still selectable", async () => {
  settings = { timezone: "Mars/Olympus", cancel_policy_hours: 24 };
  stubApi();
  renderForm();
  expect(await screen.findByLabelText("Часовой пояс")).toHaveValue("Mars/Olympus");
});

test("422 lands on the field", async () => {
  putResponse = () =>
    jsonResponse(422, {
      error: {
        code: "validation_error",
        message: "Проверьте данные",
        details: {
          fields: [{ loc: ["body", "timezone"], message: "Неизвестный часовой пояс" }],
        },
      },
    });
  stubApi();
  const user = userEvent.setup();
  renderForm();

  await screen.findByLabelText("Часовой пояс");
  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  expect(await screen.findByText("Неизвестный часовой пояс")).toBeInTheDocument();
  expect(toastSuccess).not.toHaveBeenCalled();
});

test("threshold outside 0-168 is rejected before the request", async () => {
  stubApi();
  const user = userEvent.setup();
  renderForm();

  const hours = await screen.findByLabelText("Порог поздней отмены, часов");
  await user.clear(hours);
  await user.type(hours, "200");
  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  expect(await screen.findByText("Не больше 168")).toBeInTheDocument();
  expect(calls("PUT")).toHaveLength(0);
});
