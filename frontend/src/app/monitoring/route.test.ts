// @vitest-environment node
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { POST } from "./route";

const SAAS_DSN = "https://pub123@o42.ingest.de.sentry.io/456";
const GLITCHTIP_DSN = "https://pubkey@errors.example.com/glitchtip/7";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockResolvedValue(
    new Response(null, { status: 200, headers: { "X-Sentry-Rate-Limits": "60::organization" } }),
  );
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  fetchMock.mockReset();
});

const envelope = (header: unknown) =>
  `${typeof header === "string" ? header : JSON.stringify(header)}\n{"type":"event"}\n{"message":"x"}`;

const call = (body: BodyInit, headers: Record<string, string> = {}) =>
  POST(
    new Request("http://web.test/monitoring", {
      method: "POST",
      body,
      headers: { "Content-Type": "text/plain;charset=UTF-8", Cookie: "session=s", ...headers },
    }),
  );

test("без DSN → 404, ничего не пересылается", async () => {
  vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "");
  const res = await call(envelope({ dsn: SAAS_DSN }));
  expect(res.status).toBe(404);
  expect(fetchMock).not.toHaveBeenCalled();
});

test("конверт нашего проекта пересылается без изменений и без cookie", async () => {
  vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", SAAS_DSN);
  const body = envelope({ dsn: SAAS_DSN, sent_at: "2026-10-13T00:00:00Z" });

  const res = await call(body);

  expect(res.status).toBe(200);
  expect(res.headers.get("x-sentry-rate-limits")).toBe("60::organization");
  expect(fetchMock).toHaveBeenCalledTimes(1);
  const [url, init] = fetchMock.mock.calls[0]!;
  expect(url).toBe("https://o42.ingest.de.sentry.io/api/456/envelope/");
  expect(init?.method).toBe("POST");
  expect(new TextDecoder().decode(init?.body as Uint8Array)).toBe(body);
  const headers = new Headers(init?.headers);
  expect(headers.get("content-type")).toBe("application/x-sentry-envelope");
  expect(headers.get("x-sentry-auth")).toContain("sentry_key=pub123");
  expect(headers.get("cookie")).toBeNull();
});

test("DSN GlitchTip с префиксом пути", async () => {
  vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", GLITCHTIP_DSN);
  const res = await call(envelope({ dsn: GLITCHTIP_DSN }));
  expect(res.status).toBe(200);
  expect(fetchMock.mock.calls[0]![0]).toBe("https://errors.example.com/glitchtip/api/7/envelope/");
});

test.each([
  ["другой проект", "https://pub123@o42.ingest.de.sentry.io/999"],
  ["другой ключ", "https://other@o42.ingest.de.sentry.io/456"],
  ["другой хост", "https://pub123@evil.example.com/456"],
  ["не DSN", "not a dsn"],
])("чужой DSN (%s) → 403", async (_name, dsn) => {
  vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", SAAS_DSN);
  const res = await call(envelope({ dsn }));
  expect(res.status).toBe(403);
  expect(fetchMock).not.toHaveBeenCalled();
});

test.each([
  ["не JSON", "{oops"],
  ["без dsn", { sent_at: "x" }],
  ["dsn не строка", { dsn: 1 }],
  ["пустое тело", ""],
])("некорректный заголовок (%s) → 400", async (_name, header) => {
  vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", SAAS_DSN);
  const res = await call(header === "" ? "" : envelope(header));
  expect(res.status).toBe(400);
  expect((await res.json()).error.code).toBe("invalid_envelope");
  expect(fetchMock).not.toHaveBeenCalled();
});

test("тело больше 1 МБ → 413", async () => {
  vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", SAAS_DSN);
  const res = await call(envelope({ dsn: SAAS_DSN }) + "x".repeat(1024 * 1024));
  expect(res.status).toBe(413);
  expect(fetchMock).not.toHaveBeenCalled();
});

test("тело больше 1 МБ без content-length (поток) → 413", async () => {
  vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", SAAS_DSN);
  const chunk = new TextEncoder().encode("x".repeat(256 * 1024));
  let sent = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (sent++ < 8) controller.enqueue(chunk);
      else controller.close();
    },
  });
  const res = await POST(
    new Request("http://web.test/monitoring", {
      method: "POST",
      body: stream,
      duplex: "half",
    } as RequestInit),
  );
  expect(res.status).toBe(413);
});

test("сетевая ошибка upstream → 502", async () => {
  vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", SAAS_DSN);
  fetchMock.mockRejectedValue(new TypeError("fetch failed"));
  const res = await call(envelope({ dsn: SAAS_DSN }));
  expect(res.status).toBe(502);
});

test("статус upstream возвращается как есть", async () => {
  vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", SAAS_DSN);
  fetchMock.mockResolvedValue(new Response(null, { status: 429, headers: { "Retry-After": "60" } }));
  const res = await call(envelope({ dsn: SAAS_DSN }));
  expect(res.status).toBe(429);
  expect(res.headers.get("retry-after")).toBe("60");
});
