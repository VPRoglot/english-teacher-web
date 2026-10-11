"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import type { z } from "zod";

import { useUpdateHeroBlock } from "@/api/generated/endpoints/admin/admin";
import type { HeroBlock, MediaOut } from "@/api/generated/model";
import { UpdateHeroBlockBody } from "@/api/generated/zod/admin/admin";
import { applyApiErrors } from "@/lib/form-errors";

import { PhotoField } from "./photo-field";
import { BlockForm, TextField, useAfterSave, zodOptions } from "./site-form";

type Values = z.infer<typeof UpdateHeroBlockBody>;

function toValues(block: HeroBlock): Values {
  return { ...block, photo_media_id: block.photo_media_id ?? null };
}

export function HeroEditor({ block, media }: { block: HeroBlock; media: MediaOut[] }) {
  const [formError, setFormError] = useState<string | null>(null);
  const update = useUpdateHeroBlock();
  const afterSave = useAfterSave();
  const {
    register,
    control,
    handleSubmit,
    setError,
    reset,
    formState: { errors },
  } = useForm<Values>({
    resolver: zodResolver(UpdateHeroBlockBody, zodOptions),
    defaultValues: toValues(block),
  });

  function onSubmit(values: Values) {
    setFormError(null);
    update.mutate(
      { data: values },
      {
        onSuccess: (saved) => {
          reset(toValues(saved));
          afterSave();
        },
        onError: (error) =>
          setFormError(
            applyApiErrors(error, setError, [
              "name",
              "title",
              "subtitle",
              "cta_text",
              "photo_media_id",
            ]),
          ),
      },
    );
  }

  return (
    <BlockForm
      title="Главный экран"
      onSubmit={handleSubmit(onSubmit)}
      formError={formError}
      pending={update.isPending}
    >
      <TextField id="hero-name" label="Имя" error={errors.name?.message} {...register("name")} />
      <TextField
        id="hero-title"
        label="Заголовок"
        error={errors.title?.message}
        {...register("title")}
      />
      <TextField
        id="hero-subtitle"
        label="Подзаголовок"
        error={errors.subtitle?.message}
        {...register("subtitle")}
      />
      <TextField
        id="hero-cta"
        label="Текст кнопки"
        error={errors.cta_text?.message}
        {...register("cta_text")}
      />
      <Controller
        control={control}
        name="photo_media_id"
        render={({ field }) => (
          <div className="flex flex-col gap-2">
            <PhotoField
              label="Фото"
              value={field.value ?? null}
              media={media}
              onChange={field.onChange}
            />
            {errors.photo_media_id && (
              <p className="text-sm text-destructive">{errors.photo_media_id.message}</p>
            )}
          </div>
        )}
      />
    </BlockForm>
  );
}
