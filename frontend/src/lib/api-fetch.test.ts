import { afterEach, expect, test, vi } from "vitest";

import { ApiError, apiFetch } from "./api-fetch";

function stubFetch(response: Response) {
  const fn = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
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

function csrfFailedResponse() {
  return new Response(JSON.stringify({ error: { code: "csrf_failed", message: "CSRF" } }), {
    status: 403,
  });
}

test("POST добавляет CSRF-заголовок из cookie", async () => {
  document.cookie = "csrf_token=tok123";
  const f = stubFetch(new Response("{}", { status: 200 }));
  await apiFetch("/api/x", { method: "POST" });
  expect(new Headers((f.mock.calls[0][1] as RequestInit).headers).get("X-CSRF-Token")).toBe(
    "tok123",
  );
});

test("FormData body is sent without forcing Content-Type", async () => {
  document.cookie = "csrf_token=tok123";
  const f = stubFetch(new Response("{}", { status: 201 }));
  const formData = new FormData();
  formData.append("file", new File(["abc"], "a.png", { type: "image/png" }));
  await apiFetch("/api/admin/media", { method: "POST", body: formData });
  const init = f.mock.calls[0][1] as RequestInit;
  expect(init.body).toBe(formData);
  const headers = new Headers(init.headers);
  // Content-Type с boundary выставит браузер сам.
  expect(headers.has("Content-Type")).toBe(false);
  expect(headers.get("X-CSRF-Token")).toBe("tok123");
});

test("GET не требует CSRF-токена", async () => {
  const f = stubFetch(new Response("{}", { status: 200 }));
  await apiFetch("/api/x");
  expect(f).toHaveBeenCalledTimes(1);
  expect(new Headers((f.mock.calls[0][1] as RequestInit).headers).has("X-CSRF-Token")).toBe(false);
});

test("без cookie сначала получает токен", async () => {
  const f = vi.fn().mockImplementation((url: string) => {
    if (url === "/api/auth/csrf") {
      document.cookie = "csrf_token=fresh";
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    return Promise.resolve(new Response("{}", { status: 200 }));
  });
  vi.stubGlobal("fetch", f);
  await apiFetch("/api/x", { method: "POST" });
  expect(f).toHaveBeenCalledTimes(2);
  expect(f.mock.calls[0][0]).toBe("/api/auth/csrf");
  expect((f.mock.calls[0][1] as RequestInit).credentials).toBe("same-origin");
  expect(new Headers((f.mock.calls[1][1] as RequestInit).headers).get("X-CSRF-Token")).toBe(
    "fresh",
  );
});

test("csrf_failed → обновить токен и повторить один раз", async () => {
  document.cookie = "csrf_token=stale";
  const f = vi.fn().mockImplementation((url: string) => {
    if (url === "/api/auth/csrf") {
      document.cookie = "csrf_token=renewed";
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    return Promise.resolve(
      document.cookie.includes("renewed")
        ? new Response("{}", { status: 200 })
        : csrfFailedResponse(),
    );
  });
  vi.stubGlobal("fetch", f);
  await expect(apiFetch("/api/x", { method: "POST" })).resolves.toEqual({});
  expect(f).toHaveBeenCalledTimes(3);
  expect(new Headers((f.mock.calls[2][1] as RequestInit).headers).get("X-CSRF-Token")).toBe(
    "renewed",
  );
});

test("csrf_failed повторяется только один раз", async () => {
  document.cookie = "csrf_token=stale";
  const f = vi.fn().mockImplementation((url: string) => {
    if (url === "/api/auth/csrf") return Promise.resolve(new Response(null, { status: 204 }));
    return Promise.resolve(csrfFailedResponse());
  });
  vi.stubGlobal("fetch", f);
  await expect(apiFetch("/api/x", { method: "POST" })).rejects.toMatchObject({
    status: 403,
    code: "csrf_failed",
  });
  expect(f).toHaveBeenCalledTimes(3);
});

test("отмена запроса не превращается в network_error", async () => {
  const ctrl = new AbortController();
  ctrl.abort();
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("aborted", "AbortError")));
  await expect(apiFetch("/api/x", { signal: ctrl.signal })).rejects.toMatchObject({
    name: "AbortError",
  });
});
