import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { Landing } from "@/components/site/landing";
import { buildJsonLd, buildMetadata, jsonLdScript } from "@/lib/seo";
import { serverEnv } from "@/lib/server-env";
import { getSite } from "@/lib/site-content";

export async function generateMetadata(): Promise<Metadata> {
  // Данные и env — только во время запроса: сборка не ходит в API.
  await connection();
  return buildMetadata(await getSite(), serverEnv("SITE_URL"));
}

export default function Home() {
  return (
    <Suspense fallback={<LandingSkeleton />}>
      <LandingContent />
    </Suspense>
  );
}

async function LandingContent() {
  await connection();
  const site = await getSite();
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: jsonLdScript(buildJsonLd(site, serverEnv("SITE_URL"))) }}
      />
      <Landing site={site} />
    </>
  );
}

function LandingSkeleton() {
  return (
    <main aria-busy="true" className="flex-1 animate-pulse">
      <div className="mx-auto grid w-full max-w-5xl gap-8 px-4 py-10 sm:px-6 md:grid-cols-2 md:py-16">
        <div className="space-y-4">
          <div className="h-4 w-32 rounded bg-muted" />
          <div className="h-10 w-full rounded bg-muted" />
          <div className="h-6 w-3/4 rounded bg-muted" />
        </div>
        <div className="mx-auto h-72 w-full max-w-xs rounded-2xl bg-muted" />
      </div>
    </main>
  );
}
