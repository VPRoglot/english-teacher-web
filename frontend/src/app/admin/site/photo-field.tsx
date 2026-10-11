"use client";

import { useId, useState } from "react";

import { useUploadMedia } from "@/api/generated/endpoints/admin/admin";
import type { MediaOut } from "@/api/generated/model";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/form-errors";

const MAX_BYTES = 5 * 1024 * 1024;

export function PhotoField({
  label,
  value,
  media,
  onChange,
}: {
  label: string;
  value: string | null;
  media: MediaOut[];
  onChange: (id: string | null) => void;
}) {
  const inputId = useId();
  const upload = useUploadMedia();
  const [uploaded, setUploaded] = useState<MediaOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  const current =
    value === null
      ? null
      : (media.find((item) => item.id === value) ?? (uploaded?.id === value ? uploaded : null));

  function onFile(file: File | undefined) {
    if (!file) return;
    setError(null);
    if (file.size > MAX_BYTES) {
      setError("Файл больше 5 МБ");
      return;
    }
    upload.mutate(
      { data: { file } },
      {
        onSuccess: (created) => {
          setUploaded(created);
          onChange(created.id);
        },
        onError: (err) => setError(errorMessage(err)),
      },
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={inputId}>{label}</Label>
      {current && (
        // eslint-disable-next-line @next/next/no-img-element -- превью из /media, оптимизация не нужна
        <img
          src={current.url}
          alt={label}
          width={current.width}
          height={current.height}
          className="max-h-48 w-auto max-w-full self-start rounded-lg border object-contain"
        />
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Input
          id={inputId}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          disabled={upload.isPending}
          className="max-w-sm"
          onChange={(event) => {
            onFile(event.target.files?.[0]);
            // Тот же файл можно выбрать повторно после ошибки.
            event.target.value = "";
          }}
        />
        {value !== null && (
          <Button type="button" variant="outline" onClick={() => onChange(null)}>
            Убрать фото
          </Button>
        )}
      </div>
      {upload.isPending && <p className="text-sm text-muted-foreground">Загружаем…</p>}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
