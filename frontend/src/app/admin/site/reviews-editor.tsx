"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { Controller, useFieldArray, useForm } from "react-hook-form";
import type { z } from "zod";

import { useUpdateReviewsBlock } from "@/api/generated/endpoints/admin/admin";
import type { MediaOut, ReviewsBlock } from "@/api/generated/model";
import {
  UpdateReviewsBlockBody,
  updateReviewsBlockBodyItemsMax,
} from "@/api/generated/zod/admin/admin";
import { Button } from "@/components/ui/button";
import { applyApiErrors } from "@/lib/form-errors";

import { ListControls, ListItem } from "./list-controls";
import { PhotoField } from "./photo-field";
import { BlockForm, TextareaField, TextField, useAfterSave, zodOptions } from "./site-form";

type Values = z.infer<typeof UpdateReviewsBlockBody>;
type Review = Values["items"][number];

const EMPTY_REVIEW: Review = { author: "", text: "", child_age: null, photo_media_id: null };

function toValues(block: ReviewsBlock): Values {
  return {
    items: block.items.map((item) => ({
      ...item,
      child_age: item.child_age ?? null,
      photo_media_id: item.photo_media_id ?? null,
    })),
  };
}

export function ReviewsEditor({ block, media }: { block: ReviewsBlock; media: MediaOut[] }) {
  const [formError, setFormError] = useState<string | null>(null);
  const update = useUpdateReviewsBlock();
  const afterSave = useAfterSave();
  const {
    register,
    control,
    handleSubmit,
    setError,
    reset,
    formState: { errors },
  } = useForm<Values>({
    resolver: zodResolver(UpdateReviewsBlockBody, zodOptions),
    defaultValues: toValues(block),
  });
  const { fields, append, remove, move } = useFieldArray({ control, name: "items" });

  function onSubmit(values: Values) {
    setFormError(null);
    update.mutate(
      { data: values },
      {
        onSuccess: (saved) => {
          reset(toValues(saved));
          afterSave();
        },
        // Ошибка неизвестного фото приходит с loc [..., "items", N, "photo_media_id"] и сообщением
        // для пользователя; на поле формы она не ложится — показываем её в общем Alert.
        onError: (error) => setFormError(applyApiErrors(error, setError, [])),
      },
    );
  }

  return (
    <BlockForm
      title="Отзывы"
      onSubmit={handleSubmit(onSubmit)}
      formError={formError}
      pending={update.isPending}
    >
      {fields.length === 0 && <p className="text-sm text-muted-foreground">Отзывов пока нет.</p>}
      {fields.map((field, index) => {
        const itemErrors = errors.items?.[index];
        const id = `review-${field.id}`;
        return (
          <ListItem
            key={field.id}
            title={`Отзыв ${index + 1}`}
            controls={
              <ListControls
                index={index}
                count={fields.length}
                noun="отзыв"
                onMoveUp={() => move(index, index - 1)}
                onMoveDown={() => move(index, index + 1)}
                onRemove={() => remove(index)}
              />
            }
          >
            <TextField
              id={`${id}-author`}
              label="Автор"
              error={itemErrors?.author?.message}
              {...register(`items.${index}.author`)}
            />
            <TextField
              id={`${id}-age`}
              label="Возраст ребёнка"
              type="number"
              inputMode="numeric"
              error={itemErrors?.child_age?.message}
              // Пустое поле — «возраст не указан»: null, а не NaN.
              {...register(`items.${index}.child_age`, {
                setValueAs: (value: string | number | null) =>
                  value === "" || value === null ? null : Number(value),
              })}
            />
            <TextareaField
              id={`${id}-text`}
              label="Текст отзыва"
              rows={4}
              error={itemErrors?.text?.message}
              {...register(`items.${index}.text`)}
            />
            <Controller
              control={control}
              name={`items.${index}.photo_media_id`}
              render={({ field: photo }) => (
                <div className="flex flex-col gap-2">
                  <PhotoField
                    label={`Фото отзыва ${index + 1}`}
                    value={photo.value ?? null}
                    media={media}
                    onChange={photo.onChange}
                  />
                  {itemErrors?.photo_media_id && (
                    <p className="text-sm text-destructive">{itemErrors.photo_media_id.message}</p>
                  )}
                </div>
              )}
            />
          </ListItem>
        );
      })}
      {errors.items?.message && <p className="text-sm text-destructive">{errors.items.message}</p>}
      <div>
        <Button
          type="button"
          variant="outline"
          disabled={fields.length >= updateReviewsBlockBodyItemsMax}
          onClick={() => append(EMPTY_REVIEW)}
        >
          Добавить отзыв
        </Button>
      </div>
    </BlockForm>
  );
}
