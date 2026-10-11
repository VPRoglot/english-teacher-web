import type { LeadDetail } from "@/api/generated/model";

export function makeLead(overrides: Partial<LeadDetail> = {}): LeadDetail {
  return {
    id: "l1",
    parent_name: "Анна Смирнова",
    child_name: "Маша",
    child_age: 8,
    phone: "+79991234567",
    contact_method: "telegram",
    messenger_handle: "@anna",
    goal: "Подтянуть разговорный английский",
    preferred_time: "Будни после 17:00",
    status: "new",
    reject_reason: null,
    tutor_comment: null,
    family_id: null,
    consent_at: "2026-10-10T09:30:00Z",
    notified_at: "2026-10-10T09:31:00Z",
    utm_source: null,
    utm_medium: null,
    utm_campaign: null,
    created_at: "2026-10-10T09:30:00Z",
    updated_at: "2026-10-10T09:30:00Z",
    history: [
      { from_status: null, to_status: "new", comment: null, changed_at: "2026-10-10T09:30:00Z" },
    ],
    ...overrides,
  };
}

export function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function errorResponse(
  status: number,
  code: string,
  message: string,
  details: Record<string, unknown> = {},
): Response {
  return jsonResponse(status, { error: { code, message, details } });
}

export function bodyOf(call: unknown[] | undefined): unknown {
  return JSON.parse(String((call?.[1] as RequestInit | undefined)?.body));
}
