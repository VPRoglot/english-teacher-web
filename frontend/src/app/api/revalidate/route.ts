import { timingSafeEqual } from "node:crypto";

import { revalidateTag } from "next/cache";

import { SITE_CONTENT_TAG } from "@/lib/site-content";

function errorResponse(status: number, code: string, message: string): Response {
  return Response.json({ error: { code, message } }, { status });
}

function isAuthorized(header: string | null, secret: string): boolean {
  const expected = Buffer.from(`Bearer ${secret}`);
  const actual = Buffer.from(header ?? "");
  // timingSafeEqual требует буферы одной длины; при разной длине — сразу отказ.
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}

/** Вызывается worker бэкенда после изменения контента лендинга. */
export async function POST(request: Request): Promise<Response> {
  const secret = process.env.REVALIDATE_SECRET;
  if (!secret) {
    return errorResponse(503, "revalidate_not_configured", "Сброс кеша не настроен");
  }
  if (!isAuthorized(request.headers.get("authorization"), secret)) {
    return errorResponse(401, "invalid_secret", "Неверный секрет");
  }
  revalidateTag(SITE_CONTENT_TAG, { expire: 0 });
  return new Response(null, { status: 204 });
}
