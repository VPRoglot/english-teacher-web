import { afterEach, expect, test, vi } from "vitest";

import sitemap from "./sitemap";

vi.mock("next/server", () => ({ connection: vi.fn() }));

afterEach(() => {
  vi.unstubAllEnvs();
});

test("sitemap lists only public pages", async () => {
  vi.stubEnv("SITE_URL", "https://anna.example");
  const entries = await sitemap();
  expect(entries.map((e) => e.url)).toEqual(["https://anna.example/", "https://anna.example/privacy"]);
});
