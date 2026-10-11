import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { LeadStatus } from "@/api/generated/model";

const toastSuccess = vi.fn();

vi.mock("sonner", () => ({ toast: { success: (message: string) => toastSuccess(message) } }));

import { bodyOf, errorResponse, jsonResponse, makeLead } from "./lead-fixture";
import { LeadStatusActions, MANUAL_TRANSITIONS } from "./lead-status-actions";

let fetchMock: ReturnType<typeof vi.fn>;
let patchResponse: () => Response;

function stubApi() {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/admin/leads/l1" && init?.method === "PATCH") return patchResponse();
    if (url === "/api/admin/leads/l1" && init?.method === "GET") return jsonResponse(200, makeLead());
    throw new Error(`unexpected fetch ${init?.method} ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function patches() {
  return fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH");
}

function renderActions(status: LeadStatus = "new") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(client, "invalidateQueries");
  render(
    <QueryClientProvider client={client}>
      <LeadStatusActions lead={makeLead({ status })} />
    </QueryClientProvider>,
  );
  return { invalidate };
}

beforeEach(() => {
  toastSuccess.mockReset();
  document.cookie = "csrf_token=t";
  patchResponse = () => jsonResponse(200, makeLead({ status: "contacted" }));
  stubApi();
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test.each([
  ["new", ["Связались", "Отказ"]],
  ["contacted", ["Отказ"]],
  ["trial_scheduled", ["Связались", "Отказ"]],
  ["rejected", ["Связались"]],
  ["converted", []],
] as [LeadStatus, string[]][])("status %s shows %j", (status, buttons) => {
  renderActions(status);
  expect(screen.queryAllByRole("button").map((button) => button.textContent)).toEqual(buttons);
});

test("contacted sends an optional comment and refreshes the lead", async () => {
  const { invalidate } = renderActions("new");
  await userEvent.click(screen.getByRole("button", { name: "Связались" }));
  await userEvent.type(screen.getByLabelText("Комментарий"), "Написала в Telegram");
  await userEvent.click(screen.getByRole("button", { name: "Подтвердить" }));

  await waitFor(() => expect(patches()).toHaveLength(1));
  expect(patches()[0][0]).toBe("/api/admin/leads/l1");
  expect(bodyOf(patches()[0])).toEqual({ status: "contacted", comment: "Написала в Telegram" });
  await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Статус обновлён"));
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["/api/admin/leads/l1"] });
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

test("contacted without a comment sends only the status", async () => {
  renderActions("new");
  await userEvent.click(screen.getByRole("button", { name: "Связались" }));
  await userEvent.click(screen.getByRole("button", { name: "Подтвердить" }));

  await waitFor(() => expect(patches()).toHaveLength(1));
  expect(bodyOf(patches()[0])).toEqual({ status: "contacted" });
});

test("reject needs a reason and sends it", async () => {
  patchResponse = () => jsonResponse(200, makeLead({ status: "rejected", reject_reason: "Дорого" }));
  renderActions("new");
  await userEvent.click(screen.getByRole("button", { name: "Отказ" }));
  await userEvent.click(screen.getByRole("button", { name: "Подтвердить" }));

  expect(await screen.findByText("Заполните поле")).toBeInTheDocument();
  expect(patches()).toHaveLength(0);

  await userEvent.type(screen.getByLabelText("Причина отказа"), "Дорого");
  await userEvent.click(screen.getByRole("button", { name: "Подтвердить" }));

  await waitFor(() => expect(patches()).toHaveLength(1));
  expect(bodyOf(patches()[0])).toEqual({ status: "rejected", reject_reason: "Дорого" });
  await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Статус обновлён"));
});

test("a whitespace-only reason is not accepted", async () => {
  renderActions("new");
  await userEvent.click(screen.getByRole("button", { name: "Отказ" }));
  await userEvent.type(screen.getByLabelText("Причина отказа"), "   ");
  await userEvent.click(screen.getByRole("button", { name: "Подтвердить" }));

  expect(await screen.findByText("Заполните поле")).toBeInTheDocument();
  expect(patches()).toHaveLength(0);
});

test("409 is shown and the lead is refreshed", async () => {
  patchResponse = () =>
    errorResponse(409, "invalid_status_transition", "Нельзя перевести заявку из этого статуса");
  const { invalidate } = renderActions("new");
  await userEvent.click(screen.getByRole("button", { name: "Связались" }));
  await userEvent.click(screen.getByRole("button", { name: "Подтвердить" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Нельзя перевести заявку из этого статуса",
  );
  expect(toastSuccess).not.toHaveBeenCalled();
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["/api/admin/leads/l1"] });
});

test("a dialog starts clean after being cancelled", async () => {
  renderActions("new");
  await userEvent.click(screen.getByRole("button", { name: "Отказ" }));
  await userEvent.type(screen.getByLabelText("Причина отказа"), "Дорого");
  await userEvent.click(screen.getByRole("button", { name: "Отмена" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

  await userEvent.click(screen.getByRole("button", { name: "Отказ" }));
  expect(screen.getByLabelText("Причина отказа")).toHaveValue("");
});

// Таблица переходов из спеки 3.2 (docs/superpowers/specs/2026-10-11-english-tutor-mvp-design.md).
const SPEC_TRANSITIONS: Record<LeadStatus, LeadStatus[]> = {
  new: ["contacted", "trial_scheduled", "rejected"],
  contacted: ["trial_scheduled", "rejected"],
  trial_scheduled: ["converted", "rejected", "contacted"],
  rejected: ["contacted"],
  converted: [],
};

test("manual transitions match the spec table", () => {
  // Вручную выставляются только contacted и rejected: trial_scheduled и converted — побочный эффект.
  const expected = Object.fromEntries(
    Object.entries(SPEC_TRANSITIONS).map(([from, targets]) => [
      from,
      targets.filter((target) => target === "contacted" || target === "rejected"),
    ]),
  );
  // Порядок задаёт интерфейс (кнопки), поэтому сравниваем как множества.
  const actual = Object.fromEntries(
    Object.entries(MANUAL_TRANSITIONS).map(([from, targets]) => [from, [...targets].sort()]),
  );
  expect(actual).toEqual(
    Object.fromEntries(Object.entries(expected).map(([from, targets]) => [from, [...targets].sort()])),
  );
});
