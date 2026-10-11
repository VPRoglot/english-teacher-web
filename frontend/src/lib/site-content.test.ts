import { cacheTag } from "next/cache";
import { afterEach, expect, test, vi } from "vitest";

import { siteFixture } from "@/test/site-fixture";

import { getSite } from "./site-content";

vi.mock("next/cache", () => ({ cacheTag: vi.fn(), cacheLife: vi.fn() }));

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

test("fetches public site from internal API and tags the cache", async () => {
  vi.stubEnv("API_INTERNAL_URL", "http://api.test/");
  const fetchMock = vi.fn<typeof fetch>(async () => Response.json(siteFixture));
  vi.stubGlobal("fetch", fetchMock);

  await expect(getSite()).resolves.toEqual(siteFixture);

  expect(fetchMock.mock.calls[0][0]).toBe("http://api.test/api/public/site");
  expect(cacheTag).toHaveBeenCalledWith("site-content");
});

test("throws on error status", async () => {
  vi.stubEnv("API_INTERNAL_URL", "http://api.test");
  vi.stubGlobal("fetch", vi.fn(async () => new Response("boom", { status: 500 })));
  await expect(getSite()).rejects.toThrow("GET /api/public/site → 500");
});

test("throws on unexpected shape", async () => {
  vi.stubEnv("API_INTERNAL_URL", "http://api.test");
  vi.stubGlobal("fetch", vi.fn(async () => Response.json({ hero: {} })));
  await expect(getSite()).rejects.toThrow();
});

test("throws when API_INTERNAL_URL is missing", async () => {
  vi.stubEnv("API_INTERNAL_URL", "");
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  await expect(getSite()).rejects.toThrow(/API_INTERNAL_URL/);
  expect(fetchMock).not.toHaveBeenCalled();
});
