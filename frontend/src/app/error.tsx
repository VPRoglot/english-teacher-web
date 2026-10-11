"use client";

import { Button } from "@/components/ui/button";

export default function Error({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-4 p-6 text-center">
      <h1 className="text-2xl font-semibold tracking-tight">Не удалось загрузить страницу</h1>
      <p className="text-muted-foreground">Это временная неполадка. Попробуйте ещё раз.</p>
      <Button size="lg" onClick={() => retry()}>
        Попробовать снова
      </Button>
    </main>
  );
}
