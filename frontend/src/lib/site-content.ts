import { cacheLife, cacheTag } from "next/cache";

import type { PublicSite } from "@/api/generated/model";
import { GetPublicSiteResponse } from "@/api/generated/zod/public/public";

import { serverEnv } from "./server-env";

/** Тег кеша Next; бэкенд сбрасывает его через `POST /api/revalidate`. */
export const SITE_CONTENT_TAG = "site-content";

/**
 * Публичный контент лендинга. Результат кешируется в Next; исключение
 * выходит из `'use cache'`, поэтому ошибки в кеш не попадают.
 */
export async function getSite(): Promise<PublicSite> {
  "use cache";
  cacheTag(SITE_CONTENT_TAG);
  cacheLife({ stale: 300, revalidate: 3600, expire: 86400 });

  const response = await fetch(`${serverEnv("API_INTERNAL_URL")}/api/public/site`, {
    headers: { Accept: "application/json" },
    signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) {
    throw new Error(`GET /api/public/site → ${response.status}`);
  }
  const parsed = GetPublicSiteResponse.safeParse(await response.json());
  if (!parsed.success) {
    // Только пути и коды ошибок: значения из ответа в лог не попадают.
    const issues = parsed.error.issues.map((issue) => `${issue.path.join(".")}: ${issue.code}`);
    console.error("GET /api/public/site: ответ не соответствует схеме", issues);
    throw parsed.error;
  }
  return parsed.data;
}
