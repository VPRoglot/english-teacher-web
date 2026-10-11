// @vitest-environment node
import { NextRequest } from "next/server";
import { expect, test } from "vitest";

import { config, proxy } from "./proxy";

test("без cookie → редирект на /login с next", () => {
  const res = proxy(new NextRequest("http://localhost:3000/admin/families?x=1"));
  expect(res.headers.get("location")).toBe(
    "http://localhost:3000/login?next=%2Fadmin%2Ffamilies%3Fx%3D1",
  );
});

test("с cookie session → пропускает", () => {
  const req = new NextRequest("http://localhost:3000/cabinet", {
    headers: { cookie: "session=abc" },
  });
  expect(proxy(req).headers.get("location")).toBeNull();
});

test("matcher охватывает только /cabinet и /admin", () => {
  expect(config.matcher).toEqual(["/cabinet/:path*", "/admin/:path*"]);
});
