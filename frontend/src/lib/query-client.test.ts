import { expect, test, vi } from "vitest";

import { ApiError } from "./api-fetch";
import { makeQueryClient, shouldRetry } from "./query-client";

test.each([
  [400, false],
  [401, false],
  [404, false],
  [429, false],
  [500, true],
  [0, true],
])("shouldRetry для статуса %i → %s", (status, expected) => {
  expect(shouldRetry(0, new ApiError(status, "x", "x"))).toBe(expected);
});

test("второй повтор не делается", () => {
  expect(shouldRetry(1, new ApiError(500, "x", "x"))).toBe(false);
});

test("не-ApiError повторяется один раз", () => {
  expect(shouldRetry(0, new Error("boom"))).toBe(true);
  expect(shouldRetry(1, new Error("boom"))).toBe(false);
});

test("мутации не повторяются", () => {
  expect(makeQueryClient(() => {}).getDefaultOptions().mutations?.retry).toBe(false);
});

const unauthorized = () => Promise.reject(new ApiError(401, "unauthenticated", "Войдите"));

test("401 вызывает onUnauthenticated", async () => {
  const onUnauthenticated = vi.fn();
  const client = makeQueryClient(onUnauthenticated);
  await client.fetchQuery({ queryKey: ["me"], queryFn: unauthorized, retry: false }).catch(() => {});
  expect(onUnauthenticated).toHaveBeenCalledTimes(1);
});

test("401 с meta.skipAuthRedirect не вызывает onUnauthenticated", async () => {
  const onUnauthenticated = vi.fn();
  const client = makeQueryClient(onUnauthenticated);
  await client
    .fetchQuery({
      queryKey: ["me"],
      queryFn: unauthorized,
      retry: false,
      meta: { skipAuthRedirect: true },
    })
    .catch(() => {});
  expect(onUnauthenticated).not.toHaveBeenCalled();
});

test("не-401 ошибка не вызывает onUnauthenticated", async () => {
  const onUnauthenticated = vi.fn();
  const client = makeQueryClient(onUnauthenticated);
  await client
    .fetchQuery({
      queryKey: ["x"],
      queryFn: () => Promise.reject(new ApiError(500, "x", "x")),
      retry: false,
    })
    .catch(() => {});
  expect(onUnauthenticated).not.toHaveBeenCalled();
});

test("401 в мутации вызывает onUnauthenticated", async () => {
  const onUnauthenticated = vi.fn();
  const client = makeQueryClient(onUnauthenticated);
  await client
    .getMutationCache()
    .build(client, { mutationFn: unauthorized })
    .execute(undefined)
    .catch(() => {});
  expect(onUnauthenticated).toHaveBeenCalledTimes(1);
});
