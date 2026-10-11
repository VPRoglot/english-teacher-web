import { afterEach, expect, test, vi } from "vitest";

import { ApiError, apiFetch } from "./api-fetch";

function stubFetch(response: Response) {
  const fn = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test("возвращает JSON при 2xx", async () => {
  stubFetch(new Response(JSON.stringify({ status: "ok" }), { status: 200 }));
  await expect(apiFetch("/api/health")).resolves.toEqual({ status: "ok" });
});

test("превращает тело ошибки в ApiError", async () => {
  stubFetch(
    new Response(
      JSON.stringify({ error: { code: "not_found", message: "Не найдено", details: { id: "x" } } }),
      { status: 404, headers: { "X-Request-ID": "r1" } },
    ),
  );
  const err: unknown = await apiFetch("/api/x").catch((e: unknown) => e);
  expect(err).toBeInstanceOf(ApiError);
  expect(err).toMatchObject({
    status: 404,
    code: "not_found",
    message: "Не найдено",
    details: { id: "x" },
    requestId: "r1",
  });
});

test("не-JSON ошибка → unknown_error", async () => {
  stubFetch(new Response("<html>Bad Gateway</html>", { status: 502 }));
  await expect(apiFetch("/api/x")).rejects.toMatchObject({
    status: 502,
    code: "unknown_error",
    message: "Сервер вернул ошибку 502",
  });
});

test("сетевой сбой → network_error", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
  await expect(apiFetch("/api/x")).rejects.toMatchObject({
    status: 0,
    code: "network_error",
    message: "Нет соединения с сервером",
  });
});

test("204 → undefined", async () => {
  stubFetch(new Response(null, { status: 204 }));
  await expect(apiFetch("/api/x", { method: "DELETE" })).resolves.toBeUndefined();
});

test("передаёт cookie того же origin и просит JSON", async () => {
  const f = stubFetch(new Response("{}", { status: 200 }));
  await apiFetch("/api/x");
  const init = f.mock.calls[0][1] as RequestInit;
  expect(init.credentials).toBe("same-origin");
  expect(new Headers(init.headers).get("Accept")).toBe("application/json");
});
