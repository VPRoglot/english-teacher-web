import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, test, vi } from "vitest";

import { useTutorTimeZone } from "./use-tutor-time-zone";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

function stubApi() {
  fetchMock = vi.fn(async (url: string) => {
    if (url === "/api/admin/settings" || url === "/api/me/schedule-settings") {
      return jsonResponse(200, { timezone: "Asia/Yekaterinburg", cancel_policy_hours: 24 });
    }
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function requestedUrls(): string[] {
  return fetchMock.mock.calls.map(([url]) => String(url));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test("admin reads the zone from /admin/settings, Moscow until it loads", async () => {
  stubApi();
  const { result } = renderHook(() => useTutorTimeZone("admin"), { wrapper });
  expect(result.current).toBe("Europe/Moscow");
  await waitFor(() => expect(result.current).toBe("Asia/Yekaterinburg"));
  expect(requestedUrls()).toEqual(["/api/admin/settings"]);
});

test("cabinet reads the zone from /me/schedule-settings and never asks for admin settings", async () => {
  stubApi();
  const { result } = renderHook(() => useTutorTimeZone("cabinet"), { wrapper });
  await waitFor(() => expect(result.current).toBe("Asia/Yekaterinburg"));
  expect(requestedUrls()).toEqual(["/api/me/schedule-settings"]);
});

test("falls back to Moscow when settings fail to load", async () => {
  fetchMock = vi.fn(async () => jsonResponse(500, { error: { code: "x", message: "boom" } }));
  vi.stubGlobal("fetch", fetchMock);
  const { result } = renderHook(() => useTutorTimeZone("admin"), { wrapper });
  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
  expect(result.current).toBe("Europe/Moscow");
});
