"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/form-errors";

const MOSCOW_FORMAT = new Intl.DateTimeFormat("ru-RU", {
  timeZone: "Europe/Moscow",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

/** `dd.MM.yyyy HH:mm` по московскому времени (ru-RU разделяет дату и время запятой). */
function formatMoscow(iso: string): string {
  return MOSCOW_FORMAT.format(new Date(iso)).replace(",", "");
}

export function CopyLinkCard({
  url,
  expiresAt,
  title,
}: {
  url: string;
  expiresAt: string;
  title: string;
}) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setError(null);
      setCopied(true);
    } catch (e) {
      setCopied(false);
      setError(errorMessage(e));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex gap-2">
          <Input readOnly value={url} aria-label={title} onFocus={(e) => e.currentTarget.select()} />
          <Button type="button" onClick={copy}>
            Скопировать
          </Button>
        </div>
        <p className="text-sm text-muted-foreground" role="status">
          {copied ? "Скопировано" : null}
          {error}
        </p>
        <p className="text-sm text-muted-foreground">Действует до {formatMoscow(expiresAt)}</p>
      </CardContent>
    </Card>
  );
}
