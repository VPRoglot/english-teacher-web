import type { Breadcrumb, ErrorEvent } from "@sentry/nextjs";
import { describe, expect, test } from "vitest";

import { browserSentryOptions, scrubUrl, sentryOptions, tunnelFor } from "./sentry-options";

const SAAS_DSN = "https://public@o123.ingest.sentry.io/456";
const SAAS_DSN_EU = "https://public@o123.ingest.de.sentry.io/456";
const GLITCHTIP_DSN = "https://public@glitchtip.example.com/7";

describe("scrubUrl — те же случаи, что scrub_text в backend", () => {
  test.each([
    ["/invite/AbC_123-x", "/invite/***"],
    ["/reset/tok", "/reset/***"],
    ["/api/auth/invitations/tok/accept", "/api/auth/invitations/***/accept"],
    ["/api/auth/password-resets/tok", "/api/auth/password-resets/***"],
    [
      "https://api.telegram.org/bot123:AAx/sendMessage",
      "https://api.telegram.org/bot***/sendMessage",
    ],
    ["https://site.ru/invite/tok?x=1", "https://site.ru/invite/***?x=1"],
    ["/api/health", "/api/health"],
    ["обычный текст", "обычный текст"],
  ])("%s → %s", (raw, expected) => {
    expect(scrubUrl(raw)).toBe(expected);
  });

  test("маскирует все вхождения", () => {
    expect(scrubUrl("from /invite/a to /reset/b#x")).toBe("from /invite/*** to /reset/***#x");
  });
});

describe("sentryOptions", () => {
  test("без DSN отправка выключена", () => {
    expect(sentryOptions({}).enabled).toBe(false);
  });

  test("пустой DSN — то же, что незаданный", () => {
    const options = sentryOptions({ dsn: "", release: "" });
    expect(options.enabled).toBe(false);
    expect(options.dsn).toBeUndefined();
    expect(options.release).toBeUndefined();
  });

  test("с DSN: без PII и без трассировки", () => {
    const options = sentryOptions({ dsn: SAAS_DSN, environment: "production", release: "sha-1" });
    expect(options).toMatchObject({
      enabled: true,
      dsn: SAAS_DSN,
      environment: "production",
      release: "sha-1",
      sendDefaultPii: false,
      tracesSampleRate: 0,
    });
  });

  test("beforeSend маскирует URL, transaction и заголовки, удаляет cookies", () => {
    const event = {
      transaction: "/api/auth/invitations/tok1/accept",
      request: {
        url: "https://site.ru/invite/tok2",
        cookies: { session: "s" },
        headers: {
          Cookie: "session=s",
          "X-CSRF-Token": "c",
          Authorization: "Bearer x",
          Referer: "https://site.ru/reset/tok3",
          Accept: "*/*",
        },
      },
      breadcrumbs: [{ category: "fetch", data: { url: "/api/auth/password-resets/tok4" } }],
      exception: { values: [{ type: "Error", value: "GET /invite/tok5 failed" }] },
    } as unknown as ErrorEvent;

    const result = sentryOptions({ dsn: SAAS_DSN }).beforeSend(event) as ErrorEvent;

    expect(result.transaction).toBe("/api/auth/invitations/***/accept");
    expect(result.request?.url).toBe("https://site.ru/invite/***");
    expect(result.request).not.toHaveProperty("cookies");
    expect(result.request?.headers).toEqual({
      Referer: "https://site.ru/reset/***",
      Accept: "*/*",
    });
    expect(result.breadcrumbs?.[0]?.data?.url).toBe("/api/auth/password-resets/***");
    expect(result.exception?.values?.[0]?.value).toBe("GET /invite/*** failed");
  });

  test("beforeBreadcrumb маскирует навигацию", () => {
    const crumb: Breadcrumb = {
      category: "navigation",
      data: { from: "/invite/abc", to: "/reset/def?x=1" },
    };

    const result = sentryOptions({ dsn: SAAS_DSN }).beforeBreadcrumb(crumb);

    expect(result?.data).toEqual({ from: "/invite/***", to: "/reset/***?x=1" });
  });

  test("beforeBreadcrumb маскирует URL запроса", () => {
    const crumb: Breadcrumb = {
      category: "fetch",
      data: { method: "GET", url: "/api/auth/invitations/tok", status_code: 200 },
    };

    expect(sentryOptions({ dsn: SAAS_DSN }).beforeBreadcrumb(crumb)?.data).toEqual({
      method: "GET",
      url: "/api/auth/invitations/***",
      status_code: 200,
    });
  });
});

describe("браузер: только через туннель /monitoring", () => {
  test("tunnelFor строит путь туннеля для DSN sentry.io", () => {
    expect(tunnelFor(SAAS_DSN)).toBe("/monitoring?o=123&p=456");
    expect(tunnelFor(SAAS_DSN_EU)).toBe("/monitoring?o=123&p=456&r=de");
  });

  test("tunnelFor не умеет DSN вне sentry.io", () => {
    expect(tunnelFor(GLITCHTIP_DSN)).toBeUndefined();
    expect(tunnelFor("не dsn")).toBeUndefined();
  });

  test("события идут в туннель, без cookie", () => {
    const options = browserSentryOptions({ dsn: SAAS_DSN });
    expect(options.enabled).toBe(true);
    expect(options.tunnel).toBe("/monitoring?o=123&p=456");
    expect(options.transportOptions).toEqual({ fetchOptions: { credentials: "omit" } });
  });

  test("DSN вне sentry.io отключает браузерный Sentry: CSP не пустит запрос напрямую", () => {
    const options = browserSentryOptions({ dsn: GLITCHTIP_DSN });
    expect(options.enabled).toBe(false);
    expect(options.tunnel).toBeUndefined();
  });

  test("без трассировки в браузере: BrowserTracing убран", () => {
    const options = browserSentryOptions({ dsn: SAAS_DSN });
    const integrations = [{ name: "BrowserTracing" }, { name: "Breadcrumbs" }];
    expect(options.integrations(integrations as never)).toEqual([{ name: "Breadcrumbs" }]);
  });
});
