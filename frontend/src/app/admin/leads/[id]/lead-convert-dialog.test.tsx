import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { getGetDashboardQueryKey, getListLeadsQueryKey } from "@/api/generated/endpoints/admin/admin";
import type { LeadStatus } from "@/api/generated/model";

const toastSuccess = vi.fn();

vi.mock("sonner", () => ({ toast: { success: (message: string) => toastSuccess(message) } }));

import { LeadConvertDialog } from "./lead-convert-dialog";
import { bodyOf, errorResponse, jsonResponse, makeLead } from "./lead-fixture";

const CONVERT_URL = "/api/admin/leads/l1/convert";
const converted = {
  family_id: "f9",
  invitation: { url: "https://example.com/invite/abc", expires_at: "2026-10-20T09:00:00Z" },
};

let fetchMock: ReturnType<typeof vi.fn>;
let convertResponse: () => Response;

function converts() {
  return fetchMock.mock.calls.filter(([url, init]) => url === CONVERT_URL && init?.method === "POST");
}

function renderDialog(status: LeadStatus = "trial_scheduled") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(client, "invalidateQueries");
  render(
    <QueryClientProvider client={client}>
      <LeadConvertDialog lead={makeLead({ status })} />
    </QueryClientProvider>,
  );
  return { invalidate };
}

beforeEach(() => {
  toastSuccess.mockReset();
  document.cookie = "csrf_token=t";
  convertResponse = () => jsonResponse(201, converted);
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === CONVERT_URL && init?.method === "POST") return convertResponse();
    if (url === "/api/admin/leads/l1" && init?.method === "GET") return jsonResponse(200, makeLead());
    throw new Error(`unexpected fetch ${init?.method} ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test("disabled until trial is scheduled", () => {
  renderDialog("new");
  expect(screen.getByRole("button", { name: "Конвертировать в ученика" })).toBeDisabled();
  expect(screen.getByText("Сначала назначьте пробное занятие")).toBeInTheDocument();
});

test("enabled without a hint when the trial is scheduled", () => {
  renderDialog("trial_scheduled");
  expect(screen.getByRole("button", { name: "Конвертировать в ученика" })).toBeEnabled();
  expect(screen.queryByText("Сначала назначьте пробное занятие")).not.toBeInTheDocument();
});

test("prefilled from lead and shows invitation link", async () => {
  const { invalidate } = renderDialog();
  await userEvent.click(screen.getByRole("button", { name: "Конвертировать в ученика" }));

  expect(screen.getByLabelText("Семья")).toHaveValue("Семья Маша");
  expect(screen.getByLabelText("Имя ребёнка")).toHaveValue("Маша");
  expect(screen.getByLabelText("ФИО родителя")).toHaveValue("Анна Смирнова");
  expect(screen.getByLabelText("Телефон родителя")).toHaveValue("+79991234567");

  await userEvent.click(screen.getByRole("button", { name: "Конвертировать" }));

  await waitFor(() => expect(converts()).toHaveLength(1));
  expect(bodyOf(converts()[0])).toEqual({
    family_name: "Семья Маша",
    child: { full_name: "Маша", birth_year: null, english_level: null, default_meeting_url: null },
    parent: { full_name: "Анна Смирнова", phone: "+79991234567" },
  });

  const dialog = screen.getByRole("dialog");
  expect(await within(dialog).findByLabelText("Ссылка-приглашение")).toHaveValue(
    "https://example.com/invite/abc",
  );
  expect(within(dialog).getByRole("link", { name: "Открыть семью" })).toHaveAttribute(
    "href",
    "/admin/families/f9",
  );
  expect(within(dialog).queryByLabelText("Семья")).not.toBeInTheDocument();
  expect(toastSuccess).toHaveBeenCalledWith("Заявка преобразована в семью");
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["/api/admin/leads/l1"] });
  expect(invalidate).toHaveBeenCalledWith({ queryKey: getGetDashboardQueryKey() });
});

test("sends edited values and the optional child fields", async () => {
  renderDialog();
  await userEvent.click(screen.getByRole("button", { name: "Конвертировать в ученика" }));

  const family = screen.getByLabelText("Семья");
  await userEvent.clear(family);
  await userEvent.type(family, "Семья Смирновых");
  await userEvent.type(screen.getByLabelText("Год рождения"), "2017");
  await userEvent.type(screen.getByLabelText("Ссылка на занятия"), "https://meet.example.com/masha");
  await userEvent.click(screen.getByRole("button", { name: "Конвертировать" }));

  await waitFor(() => expect(converts()).toHaveLength(1));
  expect(bodyOf(converts()[0])).toMatchObject({
    family_name: "Семья Смирновых",
    child: {
      full_name: "Маша",
      birth_year: 2017,
      default_meeting_url: "https://meet.example.com/masha",
    },
  });
});

test("client validation blocks the request", async () => {
  renderDialog();
  await userEvent.click(screen.getByRole("button", { name: "Конвертировать в ученика" }));
  await userEvent.clear(screen.getByLabelText("Семья"));
  await userEvent.type(screen.getByLabelText("Год рождения"), "17");
  await userEvent.click(screen.getByRole("button", { name: "Конвертировать" }));

  expect(await screen.findByText("Заполните поле")).toBeInTheDocument();
  expect(screen.getByText("Введите год из четырёх цифр")).toBeInTheDocument();
  expect(converts()).toHaveLength(0);
});

test("409 is shown in the form and the lead and the list are refreshed", async () => {
  convertResponse = () =>
    errorResponse(409, "lead_not_convertible", "Конвертировать можно только заявку с назначенным пробным");
  const { invalidate } = renderDialog();
  await userEvent.click(screen.getByRole("button", { name: "Конвертировать в ученика" }));
  await userEvent.click(screen.getByRole("button", { name: "Конвертировать" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Конвертировать можно только заявку с назначенным пробным",
  );
  expect(screen.getByLabelText("Семья")).toBeInTheDocument();
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["/api/admin/leads/l1"] });
  expect(invalidate).toHaveBeenCalledWith({ queryKey: getListLeadsQueryKey() });
});

test("422 is put on the field it concerns", async () => {
  convertResponse = () =>
    errorResponse(422, "validation_error", "Проверьте данные", {
      fields: [{ loc: ["body", "parent", "phone"], message: "Некорректный телефон" }],
    });
  renderDialog();
  await userEvent.click(screen.getByRole("button", { name: "Конвертировать в ученика" }));
  await userEvent.click(screen.getByRole("button", { name: "Конвертировать" }));

  expect(await screen.findByText("Некорректный телефон")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("the form starts clean after being closed", async () => {
  renderDialog();
  await userEvent.click(screen.getByRole("button", { name: "Конвертировать в ученика" }));
  await userEvent.type(screen.getByLabelText("Год рождения"), "2017");
  await userEvent.click(screen.getByRole("button", { name: "Отмена" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

  await userEvent.click(screen.getByRole("button", { name: "Конвертировать в ученика" }));
  expect(screen.getByLabelText("Год рождения")).toHaveValue("");
});
