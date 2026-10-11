"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { useUpdateAboutBlock } from "@/api/generated/endpoints/admin/admin";
import type { AboutBlock, MediaOut } from "@/api/generated/model";
import { UpdateAboutBlockBody } from "@/api/generated/zod/admin/admin";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Markdown } from "@/components/site/markdown";
import { applyApiErrors } from "@/lib/form-errors";

import { PhotoField } from "./photo-field";
import { BlockForm, useAfterSave, zodOptions } from "./site-form";

const MAX_CREDENTIALS = 20;

// Пустые пункты списка не отправляем: их нельзя сохранить, а ошибка по пустой строке только мешает.
const schema = z
  .object({
    text: z.string(),
    credentials: z.array(z.string()),
    photo_media_id: z.string().nullable(),
  })
  .transform((values): z.input<typeof UpdateAboutBlockBody> => ({
    ...values,
    credentials: values.credentials.map((item) => item.trim()).filter((item) => item !== ""),
  }))
  .pipe(UpdateAboutBlockBody);

type FormValues = z.input<typeof schema>;
type Output = z.output<typeof schema>;

function toValues(block: AboutBlock): FormValues {
  return {
    text: block.text,
    credentials: block.credentials,
    photo_media_id: block.photo_media_id ?? null,
  };
}

export function AboutEditor({ block, media }: { block: AboutBlock; media: MediaOut[] }) {
  const [formError, setFormError] = useState<string | null>(null);
  const [preview, setPreview] = useState(false);
  const update = useUpdateAboutBlock();
  const afterSave = useAfterSave();
  const {
    register,
    control,
    handleSubmit,
    setError,
    reset,
    formState: { errors },
  } = useForm<FormValues, unknown, Output>({
    resolver: zodResolver(schema, zodOptions),
    defaultValues: toValues(block),
  });
  const text = useWatch({ control, name: "text" });

  function onSubmit(values: Output) {
    setFormError(null);
    update.mutate(
      { data: values },
      {
        onSuccess: (saved) => {
          reset(toValues(saved));
          afterSave();
        },
        onError: (error) =>
          setFormError(applyApiErrors(error, setError, ["text", "credentials", "photo_media_id"])),
      },
    );
  }

  return (
    <BlockForm
      title="Обо мне"
      onSubmit={handleSubmit(onSubmit)}
      formError={formError}
      pending={update.isPending}
    >
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <Label htmlFor="about-text">Текст</Label>
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-pressed={preview}
            onClick={() => setPreview((value) => !value)}
          >
            Предпросмотр
          </Button>
        </div>
        {preview ? (
          <div className="rounded-lg border p-3">
            <Markdown>{text}</Markdown>
          </div>
        ) : (
          <Textarea
            id="about-text"
            rows={8}
            aria-invalid={errors.text ? true : undefined}
            {...register("text")}
          />
        )}
        <p className="text-xs text-muted-foreground">Поддерживается Markdown: **жирный**, списки, ссылки.</p>
        {errors.text && <p className="text-sm text-destructive">{errors.text.message}</p>}
      </div>

      <Controller
        control={control}
        name="credentials"
        render={({ field }) => {
          const items = field.value;
          return (
            <div className="flex flex-col gap-2">
              <Label>Дипломы и сертификаты</Label>
              <ul className="flex flex-col gap-2">
                {items.map((item, index) => {
                  const itemError = Array.isArray(errors.credentials)
                    ? errors.credentials[index]?.message
                    : undefined;
                  return (
                    // Список редактируется по индексу и не переупорядочивается — индекс как ключ безопасен.
                    <li key={index} className="flex flex-col gap-1">
                      <div className="flex gap-2">
                        <Input
                          aria-label={`Пункт ${index + 1}`}
                          aria-invalid={itemError ? true : undefined}
                          value={item}
                          onChange={(event) =>
                            field.onChange(
                              items.map((current, i) => (i === index ? event.target.value : current)),
                            )
                          }
                        />
                        <Button
                          type="button"
                          variant="outline"
                          aria-label={`Удалить пункт ${index + 1}`}
                          onClick={() => field.onChange(items.filter((_, i) => i !== index))}
                        >
                          Удалить
                        </Button>
                      </div>
                      {itemError && <p className="text-sm text-destructive">{itemError}</p>}
                    </li>
                  );
                })}
              </ul>
              {errors.credentials?.message && (
                <p className="text-sm text-destructive">{errors.credentials.message}</p>
              )}
              <div>
                <Button
                  type="button"
                  variant="outline"
                  disabled={items.length >= MAX_CREDENTIALS}
                  onClick={() => field.onChange([...items, ""])}
                >
                  Добавить
                </Button>
              </div>
            </div>
          );
        }}
      />

      <Controller
        control={control}
        name="photo_media_id"
        render={({ field }) => (
          <div className="flex flex-col gap-2">
            <PhotoField label="Фото" value={field.value} media={media} onChange={field.onChange} />
            {errors.photo_media_id && (
              <p className="text-sm text-destructive">{errors.photo_media_id.message}</p>
            )}
          </div>
        )}
      />
    </BlockForm>
  );
}
