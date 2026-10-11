import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { PrivacyPolicy } from "@/components/site/privacy-policy";
import { SiteFooter } from "@/components/site/site-footer";
import { SiteHeader } from "@/components/site/site-header";
import { serverEnv } from "@/lib/server-env";
import { getSite } from "@/lib/site-content";

export async function generateMetadata(): Promise<Metadata> {
  // metadataBase нужен, чтобы canonical был абсолютным; SITE_URL — только во время запроса.
  await connection();
  return {
    metadataBase: new URL(serverEnv("SITE_URL")),
    title: "Политика обработки персональных данных",
    alternates: { canonical: "/privacy" },
  };
}

export default function PrivacyPage() {
  return (
    <Suspense fallback={<PrivacySkeleton />}>
      <PrivacyContent />
    </Suspense>
  );
}

async function PrivacyContent() {
  // Данные и env — только во время запроса: сборка не ходит в API.
  await connection();
  const { hero, contacts } = await getSite();
  return (
    <>
      <SiteHeader name={hero.name} ctaText={hero.cta_text} nav={[]} homeHref="/" />
      <main className="flex-1">
        <PrivacyPolicy operatorName={hero.name} contacts={contacts} />
      </main>
      <SiteFooter name={hero.name} />
    </>
  );
}

function PrivacySkeleton() {
  return (
    <main aria-busy="true" className="flex-1 animate-pulse">
      <div className="mx-auto w-full max-w-3xl space-y-4 px-4 py-10 sm:px-6">
        <div className="h-9 w-3/4 rounded bg-muted" />
        <div className="h-4 w-full rounded bg-muted" />
        <div className="h-4 w-5/6 rounded bg-muted" />
      </div>
    </main>
  );
}
