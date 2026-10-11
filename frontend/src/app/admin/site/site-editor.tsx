"use client";

import { useGetSiteBlocks } from "@/api/generated/endpoints/admin/admin";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import { errorMessage } from "@/lib/form-errors";

import { AboutEditor } from "./about-editor";
import { ContactsEditor } from "./contacts-editor";
import { HeroEditor } from "./hero-editor";

function Skeleton() {
  return (
    <div role="status" aria-label="Загрузка" className="animate-pulse space-y-4">
      <div className="h-64 rounded-xl bg-muted" />
      <div className="h-64 rounded-xl bg-muted" />
      <div className="h-48 rounded-xl bg-muted" />
    </div>
  );
}

export function SiteEditor() {
  const query = useGetSiteBlocks();
  const blocks = query.data;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Сайт</h1>
        <a
          href="/"
          target="_blank"
          rel="noopener noreferrer"
          className={buttonVariants({ variant: "outline" })}
        >
          Открыть сайт
        </a>
      </div>
      {blocks ? (
        <>
          <HeroEditor block={blocks.hero} media={blocks.media} />
          <AboutEditor block={blocks.about} media={blocks.media} />
          <ContactsEditor block={blocks.contacts} />
        </>
      ) : query.error ? (
        <Alert variant="destructive">
          <AlertDescription>{errorMessage(query.error)}</AlertDescription>
        </Alert>
      ) : (
        <Skeleton />
      )}
    </div>
  );
}
