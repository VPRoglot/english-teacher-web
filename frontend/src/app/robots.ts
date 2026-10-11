import type { MetadataRoute } from "next";
import { connection } from "next/server";

import { serverEnv } from "@/lib/server-env";

export default async function robots(): Promise<MetadataRoute.Robots> {
  // SITE_URL читается только во время запроса: сборка не зависит от env.
  await connection();
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/admin", "/cabinet", "/invite", "/reset", "/login", "/api"],
      },
    ],
    sitemap: `${serverEnv("SITE_URL")}/sitemap.xml`,
  };
}
