import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const toastSuccess = vi.fn();
vi.mock("sonner", () => ({ toast: { success: (message: string) => toastSuccess(message) } }));

import type { ContactsBlock } from "@/api/generated/model";

import { ContactsEditor } from "./contacts-editor";

const contacts: ContactsBlock = {
  email: "anna@example.com",
  phone: "+7 900 000-00-00",
  telegram: "@anna",
  whatsapp: null,
  working_hours_text: "Пн-Пт 10:00-20:00",
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

function stubApi(respond: (body: ContactsBlock) => ContactsBlock) {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/admin/site-blocks/contacts" && init?.method === "PUT") {
      return jsonResponse(200, respond(JSON.parse(String(init.body))));
    }
    if (url === "/api/admin/site-blocks") return jsonResponse(200, {});
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function lastPutBody(): ContactsBlock {
  const call = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
  return JSON.parse(String(call?.[1].body));
}

function renderEditor() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ContactsEditor block={contacts} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  toastSuccess.mockReset();
  document.cookie = "csrf_token=t";
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrf_token=; max-age=0";
});

test("empty fields are sent as null", async () => {
  stubApi((body) => body);
  const user = userEvent.setup();
  renderEditor();

  await user.clear(screen.getByLabelText("Telegram"));
  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
  expect(lastPutBody()).toEqual({
    email: "anna@example.com",
    phone: "+7 900 000-00-00",
    telegram: null,
    whatsapp: null,
    working_hours_text: "Пн-Пт 10:00-20:00",
  });
});

test("blank email and working hours do not block saving", async () => {
  stubApi((body) => body);
  const user = userEvent.setup();
  renderEditor();

  await user.clear(screen.getByLabelText("Email"));
  await user.clear(screen.getByLabelText("Часы работы"));
  await user.type(screen.getByLabelText("WhatsApp"), "   ");
  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
  expect(lastPutBody()).toMatchObject({ email: null, working_hours_text: null, whatsapp: null });
});

test("invalid email is rejected on the client", async () => {
  stubApi((body) => body);
  const user = userEvent.setup();
  renderEditor();

  await user.clear(screen.getByLabelText("Email"));
  await user.type(screen.getByLabelText("Email"), "не-почта");
  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  expect(await screen.findByText("Некорректный email")).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
});

test("normalized values from the server are put back into the form", async () => {
  stubApi((body) => ({ ...body, telegram: "@anna_tutor" }));
  const user = userEvent.setup();
  renderEditor();

  await user.type(screen.getByLabelText("Telegram"), "_x");
  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  await waitFor(() => expect(screen.getByLabelText("Telegram")).toHaveValue("@anna_tutor"));
});
