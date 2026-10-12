"use client";

import { useId, useState } from "react";

import { Markdown } from "@/components/site/markdown";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

type Props = {
  label: string;
  description?: string;
  value: string;
  onChange: (value: string) => void;
  maxLength?: number;
};

type Mode = "text" | "preview";

/**
 * Поле Markdown с вкладками «Текст» и «Предпросмотр».
 * Предпросмотр рисует тот же `Markdown`, что и сайт: сырой HTML не выводится.
 */
export function MarkdownEditor({ label, description, value, onChange, maxLength }: Props) {
  const id = useId();
  const [mode, setMode] = useState<Mode>("text");
  const descriptionId = `${id}-description`;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Label htmlFor={`${id}-text`}>{label}</Label>
        <div role="tablist" aria-label={`Режим: ${label}`} className="flex gap-1">
          <Button
            type="button"
            role="tab"
            size="sm"
            variant={mode === "text" ? "secondary" : "ghost"}
            aria-selected={mode === "text"}
            onClick={() => setMode("text")}
          >
            Текст
          </Button>
          <Button
            type="button"
            role="tab"
            size="sm"
            variant={mode === "preview" ? "secondary" : "ghost"}
            aria-selected={mode === "preview"}
            onClick={() => setMode("preview")}
          >
            Предпросмотр
          </Button>
        </div>
      </div>
      {description && (
        <p id={descriptionId} className="text-sm text-muted-foreground">
          {description}
        </p>
      )}
      {mode === "text" ? (
        <Textarea
          id={`${id}-text`}
          className="min-h-32"
          maxLength={maxLength}
          aria-describedby={description ? descriptionId : undefined}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      ) : (
        <div role="tabpanel" className="min-h-32 rounded-lg border border-input p-3 text-sm">
          {value.trim() ? (
            <Markdown>{value}</Markdown>
          ) : (
            <p className="text-muted-foreground">Пусто</p>
          )}
        </div>
      )}
    </div>
  );
}
