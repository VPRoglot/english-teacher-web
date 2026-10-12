"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { formatDateTime } from "@/lib/datetime";
import { errorMessage } from "@/lib/form-errors";

export function CopyLinkCard({
  url,
  expiresAt,
  timeZone,
  title,
}: {
  url: string;
  expiresAt: string;
  timeZone: string;
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
        <p className="text-sm text-muted-foreground">Действует до {formatDateTime(expiresAt, timeZone)}</p>
      </CardContent>
    </Card>
  );
}
