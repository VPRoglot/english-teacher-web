import { revalidateTag } from "next/cache";
import { afterEach, expect, test, vi } from "vitest";

import { POST } from "./route";

vi.mock("next/cache", () => ({ revalidateTag: vi.fn() }));

const SECRET = "dev-revalidate-secret-change-me";

const call = (auth?: string) =>
  POST(
    new Request("http://web.test/api/revalidate", {
      method: "POST",
      headers: auth ? { Authorization: auth } : {},
    }),
  );

afterEach(() => {
  vi.unstubAllEnvs();
  vi.clearAllMocks();
});

test("valid secret revalidates site-content immediately", async () => {
  vi.stubEnv("REVALIDATE_SECRET", SECRET);
  const res = await call(`Bearer ${SECRET}`);
  expect(res.status).toBe(204);
  expect(revalidateTag).toHaveBeenCalledWith("site-content", { expire: 0 });
});

test.each([undefined, "Bearer wrong", SECRET, `Bearer ${SECRET}x`])(
  "rejects %s with 401",
  async (auth) => {
    vi.stubEnv("REVALIDATE_SECRET", SECRET);
    const res = await call(auth);
    expect(res.status).toBe(401);
    expect((await res.json()).error.code).toBe("invalid_secret");
    expect(revalidateTag).not.toHaveBeenCalled();
  },
);

test("503 when secret is not configured", async () => {
  vi.stubEnv("REVALIDATE_SECRET", "");
  const res = await call(`Bearer ${SECRET}`);
  expect(res.status).toBe(503);
  expect((await res.json()).error.code).toBe("revalidate_not_configured");
  expect(revalidateTag).not.toHaveBeenCalled();
});
