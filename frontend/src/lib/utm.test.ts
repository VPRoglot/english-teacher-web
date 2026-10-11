import { beforeEach, expect, test, vi } from "vitest";

import { captureUtm, readUtm } from "./utm";

beforeEach(() => {
  sessionStorage.clear();
  vi.restoreAllMocks();
});

test("captures utm from url and reads it back", () => {
  captureUtm("?utm_source=vk&utm_campaign=autumn&x=1");
  expect(readUtm()).toEqual({ utm_source: "vk", utm_campaign: "autumn" });
});

test("url without utm keeps earlier values", () => {
  captureUtm("?utm_source=vk");
  captureUtm("?a=1");
  expect(readUtm()).toEqual({ utm_source: "vk" });
});

test("new utm replaces earlier values", () => {
  captureUtm("?utm_source=vk&utm_medium=cpc");
  captureUtm("?utm_source=tg");
  expect(readUtm()).toEqual({ utm_source: "tg" });
});

test("values are cut to 100 characters", () => {
  captureUtm(`?utm_source=${"a".repeat(150)}`);
  expect(readUtm().utm_source).toHaveLength(100);
});

test("empty storage and corrupted json read as empty", () => {
  expect(readUtm()).toEqual({});
  sessionStorage.setItem("utm", "{not json");
  expect(readUtm()).toEqual({});
  sessionStorage.setItem("utm", JSON.stringify({ utm_source: 5, evil: "x", utm_medium: "cpc" }));
  expect(readUtm()).toEqual({ utm_medium: "cpc" });
});

test("storage errors are swallowed", () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("quota");
  });
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("denied");
  });
  expect(() => captureUtm("?utm_source=vk")).not.toThrow();
  expect(readUtm()).toEqual({});
});
