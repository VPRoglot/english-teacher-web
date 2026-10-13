import type { Breadcrumb, ErrorEvent } from "@sentry/nextjs";
import { describe, expect, test, vi } from "vitest";

import {
  browserSentryOptions,
  envelopeUrl,
  parseDsn,
  scrubUrl,
  sentryOptions,
  serverSentryOptions,
} from "./sentry-options";

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

describe("scrubDeep не ломается на живых объектах console", () => {
  test("циклические data.arguments", () => {
    const cyclic: Record<string, unknown> = { url: "/invite/tok" };
    cyclic.self = cyclic;
    const crumb: Breadcrumb = {
      category: "console",
      message: "see /reset/tok",
      data: { arguments: [cyclic], logger: "console" },
    };

    const result = sentryOptions({ dsn: SAAS_DSN }).beforeBreadcrumb(crumb);

    expect(result.message).toBe("see /reset/***");
    expect(result.data?.arguments).toEqual([{ url: "/invite/***", self: "[Circular]" }]);
  });

  test("общая ссылка без цикла не считается циклом", () => {
    const shared = { url: "/invite/tok" };
    const crumb: Breadcrumb = { data: { a: shared, b: shared } };
    expect(sentryOptions({ dsn: SAAS_DSN }).beforeBreadcrumb(crumb).data).toEqual({
      a: { url: "/invite/***" },
      b: { url: "/invite/***" },
    });
  });

  test("не простые объекты (DOM-узлы, классы) не обходятся, геттеры не вызываются", () => {
    const element = document.createElement("div");
    const getter = vi.fn(() => "/invite/tok");
    class Model {
      get url() {
        return getter();
      }
    }
    const model = new Model();
    const crumb: Breadcrumb = { category: "console", data: { arguments: [element, model] } };

    const result = sentryOptions({ dsn: SAAS_DSN }).beforeBreadcrumb(crumb);

    const args = result.data?.arguments as unknown[];
    expect(args[0]).toBe(element);
    expect(args[1]).toBe(model);
    expect(getter).not.toHaveBeenCalled();
  });

  test("слишком глубокая вложенность заменяется заглушкой", () => {
    let nested: Record<string, unknown> = { url: "/invite/tok" };
    for (let i = 0; i < 20; i++) nested = { nested };
    const result = sentryOptions({ dsn: SAAS_DSN }).beforeBreadcrumb({ data: nested });
    expect(JSON.stringify(result)).toContain("[Truncated]");
    expect(JSON.stringify(result)).not.toContain("tok");
  });
});

test("серверное событие captureRequestError: заголовки в нижнем регистре", () => {
  const event = {
    transaction: "GET /invite/[token]",
    request: {
      url: "/reset/tok1",
      method: "GET",
      headers: {
        cookie: "session=s; csrf_token=c",
        referer: "https://site.ru/invite/tok2",
        "x-forwarded-for": "1.2.3.4",
        "x-real-ip": "1.2.3.4",
        "user-agent": "UA",
      },
    },
  } as unknown as ErrorEvent;

  const result = sentryOptions({ dsn: SAAS_DSN }).beforeSend(event);

  expect(result.request?.url).toBe("/reset/***");
  expect(result.request?.headers).toEqual({
    referer: "https://site.ru/invite/***",
    "user-agent": "UA",
  });
});

describe("браузер: всегда через туннель /monitoring", () => {
  test.each([SAAS_DSN, SAAS_DSN_EU, GLITCHTIP_DSN])("DSN %s → туннель, без cookie", (dsn) => {
    const options = browserSentryOptions({ dsn });
    expect(options.enabled).toBe(true);
    expect(options.tunnel).toBe("/monitoring");
    expect(options.transportOptions).toEqual({ fetchOptions: { credentials: "omit" } });
  });

  test("без DSN выключен", () => {
    expect(browserSentryOptions({ dsn: "" }).enabled).toBe(false);
  });

  test("без трассировки в браузере: BrowserTracing убран", () => {
    const options = browserSentryOptions({ dsn: SAAS_DSN });
    const integrations = [{ name: "BrowserTracing" }, { name: "Breadcrumbs" }];
    expect(options.integrations(integrations as never)).toEqual([{ name: "Breadcrumbs" }]);
  });
});

describe("сервер: без тела запроса и локальных переменных", () => {
  test("локальные переменные выключены", () => {
    const options = serverSentryOptions({ dsn: SAAS_DSN });
    expect(options).toMatchObject({ enabled: true, includeLocalVariables: false });
  });

  test("Http заменён интеграцией без тела входящих запросов", () => {
    const httpIntegration = vi.fn((options: object) => ({ name: "Http", options }));
    const options = serverSentryOptions({ dsn: SAAS_DSN }, httpIntegration as never);
    const integrations = [{ name: "Http" }, { name: "OnUncaughtException" }];
    expect(options.integrations(integrations as never)).toEqual([
      { name: "OnUncaughtException" },
      { name: "Http", options: { disableIncomingRequestSpans: true, maxRequestBodySize: "none" } },
    ]);
  });

  test("без httpIntegration (edge) список интеграций не меняется", () => {
    const options = serverSentryOptions({ dsn: SAAS_DSN });
    const integrations = [{ name: "Breadcrumbs" }];
    expect(options.integrations(integrations as never)).toEqual(integrations);
  });
});

describe("parseDsn / envelopeUrl", () => {
  test("sentry.io", () => {
    const dsn = parseDsn(SAAS_DSN_EU);
    expect(dsn).toEqual({
      protocol: "https:",
      host: "o123.ingest.de.sentry.io",
      pathPrefix: "",
      projectId: "456",
      publicKey: "public",
    });
    expect(envelopeUrl(dsn!)).toBe("https://o123.ingest.de.sentry.io/api/456/envelope/");
  });

  test("GlitchTip с портом и префиксом пути", () => {
    const dsn = parseDsn("http://key@gt.local:8000/sub/path/7");
    expect(envelopeUrl(dsn!)).toBe("http://gt.local:8000/sub/path/api/7/envelope/");
  });

  test.each([undefined, "", "не dsn", "https://host/1", "https://k@host/abc", "ftp://k@host/1"])(
    "некорректный DSN %s → undefined",
    (raw) => {
      expect(parseDsn(raw)).toBeUndefined();
    },
  );
});
