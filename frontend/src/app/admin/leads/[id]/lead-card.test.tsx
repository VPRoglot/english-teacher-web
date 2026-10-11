import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const toastSuccess = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "l1" }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock("sonner", () => ({ toast: { success: (message: string) => toastSuccess(message) } }));

import type { LeadDetail } from "@/api/generated/model";

import { LeadCard } from "./lead-card";
import { bodyOf, errorResponse, jsonResponse, makeLead } from "./lead-fixture";

let lead: LeadDetail;
let leadResponse: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;

function stubApi() {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/admin/leads/l1" && init?.method === "GET") return leadResponse();
    if (url === "/api/admin/leads/l1" && init?.method === "PATCH") return jsonResponse(200, lead);
    throw new Error(`unexpected fetch ${init?.method} ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function patches() {
  return fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH");
}

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LeadCard />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  toastSuccess.mockReset();
  document.cookie = "csrf_token=t";
  lead = makeLead();
  leadResponse = () => jsonResponse(200, lead);
  stubApi();
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test("shows fields, contact link and history", async () => {
  lead = makeLead({
    status: "contacted",
    utm_source: "yandex",
    utm_medium: "cpc",
    utm_campaign: "autumn",
    history: [
      { from_status: null, to_status: "new", comment: null, changed_at: "2026-10-10T09:30:00Z" },
      {
        from_status: "new",
        to_status: "contacted",
        comment: "Написала в Telegram",
        changed_at: "2026-10-11T10:00:00Z",
      },
    ],
  });
  renderCard();

  expect(await screen.findByRole("heading", { name: "Анна Смирнова" })).toBeInTheDocument();
  expect(screen.getByText("Связались", { selector: "[data-slot=badge]" })).toBeInTheDocument();
  expect(screen.getByText("Маша, 8 лет")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Telegram · +79991234567" })).toHaveAttribute(
    "href",
    "https://t.me/anna_en",
  );
  expect(screen.getByText("Подтянуть разговорный английский")).toBeInTheDocument();
  expect(screen.getByText("Будни после 17:00")).toBeInTheDocument();
  expect(screen.getByText("yandex / cpc / autumn")).toBeInTheDocument();
  expect(screen.getByText("10.10.2026 12:30")).toBeInTheDocument();

  const history = screen.getByRole("heading", { name: "История" }).closest("section") as HTMLElement;
  const items = within(history).getAllByRole("listitem");
  expect(items).toHaveLength(2);
  expect(items[0]).toHaveTextContent("10.10.2026 12:30 · Заявка получена");
  expect(items[1]).toHaveTextContent("11.10.2026 13:00 · Новая → Связались · Написала в Telegram");
});

test("omits empty optional fields and UTM", async () => {
  lead = makeLead({ goal: null, preferred_time: null, messenger_handle: null });
  renderCard();
  await screen.findByRole("heading", { name: "Анна Смирнова" });
  expect(screen.queryByText("UTM")).not.toBeInTheDocument();
  expect(screen.queryByText("Цель")).not.toBeInTheDocument();
  expect(screen.queryByText("Удобное время")).not.toBeInTheDocument();
});

test("shows the reject reason", async () => {
  lead = makeLead({ status: "rejected", reject_reason: "Дорого" });
  renderCard();
  expect(await screen.findByText("Дорого")).toBeInTheDocument();
  expect(screen.getByText("Причина отказа")).toBeInTheDocument();
});

test("saves tutor comment", async () => {
  lead = makeLead({ tutor_comment: "Перезвонить в пятницу" });
  renderCard();

  const comment = await screen.findByLabelText("Комментарий репетитора");
  expect(comment).toHaveValue("Перезвонить в пятницу");
  expect(screen.getByRole("button", { name: "Сохранить комментарий" })).toBeDisabled();

  await userEvent.clear(comment);
  await userEvent.type(comment, "Договорились на субботу");
  await userEvent.click(screen.getByRole("button", { name: "Сохранить комментарий" }));

  await waitFor(() => expect(patches()).toHaveLength(1));
  expect(bodyOf(patches()[0])).toEqual({ tutor_comment: "Договорились на субботу" });
  await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Комментарий сохранён"));
});

test("the comment can be cleared", async () => {
  lead = makeLead({ tutor_comment: "Перезвонить" });
  renderCard();
  await userEvent.clear(await screen.findByLabelText("Комментарий репетитора"));
  await userEvent.click(screen.getByRole("button", { name: "Сохранить комментарий" }));

  await waitFor(() => expect(patches()).toHaveLength(1));
  expect(bodyOf(patches()[0])).toEqual({ tutor_comment: "" });
});

test("converted lead links to its family", async () => {
  lead = makeLead({ status: "converted", family_id: "f9" });
  renderCard();

  expect(await screen.findByRole("link", { name: "Открыть семью" })).toHaveAttribute(
    "href",
    "/admin/families/f9",
  );
  expect(screen.queryByRole("button", { name: "Конвертировать в ученика" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Связались" })).not.toBeInTheDocument();
});

test("a trial_scheduled lead can be converted", async () => {
  lead = makeLead({ status: "trial_scheduled" });
  renderCard();
  expect(await screen.findByRole("button", { name: "Конвертировать в ученика" })).toBeEnabled();
});

test("shows the error when the lead cannot be loaded", async () => {
  leadResponse = () => errorResponse(404, "not_found", "Заявка не найдена");
  renderCard();
  expect(await screen.findByText("Заявка не найдена")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "К списку заявок" })).toHaveAttribute("href", "/admin/leads");
});
