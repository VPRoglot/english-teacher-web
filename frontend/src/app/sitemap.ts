import type { MetadataRoute } from "next";
import { connection } from "next/server";

import { serverEnv } from "@/lib/server-env";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  // SITE_URL читается только во время запроса: сборка не зависит от env.
  await connection();
  const siteUrl = serverEnv("SITE_URL");
  return [
    { url: `${siteUrl}/`, changeFrequency: "monthly", priority: 1 },
    { url: `${siteUrl}/privacy`, changeFrequency: "yearly", priority: 0.3 },
  ];
}
