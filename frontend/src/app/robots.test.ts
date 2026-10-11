import { afterEach, expect, test, vi } from "vitest";

import robots from "./robots";

vi.mock("next/server", () => ({ connection: vi.fn() }));

afterEach(() => {
  vi.unstubAllEnvs();
});

test("robots closes private zones and points to sitemap", async () => {
  vi.stubEnv("SITE_URL", "https://anna.example/");
  expect(await robots()).toEqual({
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/admin", "/cabinet", "/invite", "/reset", "/login", "/api"],
      },
    ],
    sitemap: "https://anna.example/sitemap.xml",
  });
});
