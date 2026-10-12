import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, test, vi } from "vitest";

import {
  useTutorTimeZone,
  useTutorTimeZoneReady,
  useTutorTimeZoneStatus,
} from "./use-tutor-time-zone";

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

test("ready turns true once the admin settings are loaded, with no extra request", async () => {
  stubApi();
  const { result } = renderHook(
    () => ({ zone: useTutorTimeZone("admin"), ready: useTutorTimeZoneReady("admin") }),
    { wrapper },
  );
  expect(result.current).toEqual({ zone: "Europe/Moscow", ready: false });
  await waitFor(() => expect(result.current.ready).toBe(true));
  expect(result.current.zone).toBe("Asia/Yekaterinburg");
  expect(requestedUrls()).toEqual(["/api/admin/settings"]);
});

test("ready follows the cabinet settings and never asks for admin settings", async () => {
  stubApi();
  const { result } = renderHook(() => useTutorTimeZoneReady("cabinet"), { wrapper });
  expect(result.current).toBe(false);
  await waitFor(() => expect(result.current).toBe(true));
  expect(requestedUrls()).toEqual(["/api/me/schedule-settings"]);
});

test("ready stays false when settings fail to load", async () => {
  fetchMock = vi.fn(async () => jsonResponse(500, { error: { code: "x", message: "boom" } }));
  vi.stubGlobal("fetch", fetchMock);
  const { result } = renderHook(() => useTutorTimeZoneReady("admin"), { wrapper });
  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
  expect(result.current).toBe(false);
});

test("status: loading, then ready, without an error", async () => {
  stubApi();
  const { result } = renderHook(() => useTutorTimeZoneStatus("admin"), { wrapper });
  expect(result.current).toEqual({ timeZone: "Europe/Moscow", ready: false, error: false });
  await waitFor(() => expect(result.current.ready).toBe(true));
  expect(result.current).toEqual({ timeZone: "Asia/Yekaterinburg", ready: true, error: false });
  expect(requestedUrls()).toEqual(["/api/admin/settings"]);
});

test("status: a load failure is exposed as an error, not as an endless loading", async () => {
  fetchMock = vi.fn(async () => jsonResponse(500, { error: { code: "x", message: "boom" } }));
  vi.stubGlobal("fetch", fetchMock);
  const { result } = renderHook(() => useTutorTimeZoneStatus("admin"), { wrapper });
  await waitFor(() => expect(result.current.error).toBe(true));
  expect(result.current).toEqual({ timeZone: "Europe/Moscow", ready: false, error: true });
});

test("status for the cabinet never asks for admin settings", async () => {
  stubApi();
  const { result } = renderHook(() => useTutorTimeZoneStatus("cabinet"), { wrapper });
  await waitFor(() => expect(result.current.ready).toBe(true));
  expect(requestedUrls()).toEqual(["/api/me/schedule-settings"]);
});
