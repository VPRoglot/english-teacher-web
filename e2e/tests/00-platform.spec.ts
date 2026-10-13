import { request as playwrightRequest } from "@playwright/test";

import { BASE_URL } from "../env";
import { expect, test } from "../fixtures";

test.describe("платформа за nginx", () => {
  test("закрытый раздел без сессии ведёт на https://tutor.test/login", async () => {
    // Без cookie сессии (иначе контекст унаследовал бы сессию репетитора из `use.storageState`)
    // и без следования редиректу: проверяется сам ответ за прокси.
    const anonymous = await playwrightRequest.newContext({
      baseURL: BASE_URL,
      ignoreHTTPSErrors: true,
      storageState: { cookies: [], origins: [] },
    });
    try {
      const response = await anonymous.get("/cabinet", { maxRedirects: 0 });
      expect([302, 307]).toContain(response.status());
      const location = response.headers()["location"] ?? "";
      expect(location).not.toBe("");
      // Next отдаёт относительный Location; браузер разрешает его от адреса запроса. Абсолютный
      // адрес не должен указывать на внутренний хост или http (web:3000, localhost и т. п.).
      expect(new URL(location, response.url()).href).toMatch(/^https:\/\/tutor\.test\/login/);
      expect(location).toMatch(/^(\/login|https:\/\/tutor\.test\/login)/);
    } finally {
      await anonymous.dispose();
    }
  });

  test("на главной есть CSP и HSTS", async ({ request }) => {
    const response = await request.get("/");
    expect(response.status()).toBe(200);
    const headers = response.headers();
    expect(headers["strict-transport-security"]).toContain("max-age=");
    expect(headers["content-security-policy"]).toContain("default-src 'self'");
    expect(headers["content-security-policy"]).toContain("frame-ancestors 'none'");
  });

  test("/api/health/ready отвечает 200", async ({ request }) => {
    const response = await request.get("/api/health/ready");
    expect(response.status()).toBe(200);
    expect(await response.json()).toMatchObject({ status: "ok" });
  });
});
