"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import type { z } from "zod";

import { useUpdateServicesBlock } from "@/api/generated/endpoints/admin/admin";
import type { ServicesBlock } from "@/api/generated/model";
import {
  UpdateServicesBlockBody,
  updateServicesBlockBodyItemsMax,
} from "@/api/generated/zod/admin/admin";
import { Button } from "@/components/ui/button";
import { applyApiErrors } from "@/lib/form-errors";

import { ListControls, ListItem } from "./list-controls";
import { BlockForm, TextareaField, TextField, useAfterSave, zodOptions } from "./site-form";

type Values = z.infer<typeof UpdateServicesBlockBody>;

// Новая услуга: числа пустые (NaN), пока репетитор их не введёт, — разумных значений по умолчанию нет.
const EMPTY_SERVICE: Values["items"][number] = {
  title: "",
  description: "",
  duration_min: Number.NaN,
  price_rub: Number.NaN,
  format: "",
};

export function ServicesEditor({ block }: { block: ServicesBlock }) {
  const [formError, setFormError] = useState<string | null>(null);
  const update = useUpdateServicesBlock();
  const afterSave = useAfterSave();
  const {
    register,
    control,
    handleSubmit,
    setError,
    reset,
    formState: { errors },
  } = useForm<Values>({
    resolver: zodResolver(UpdateServicesBlockBody, zodOptions),
    defaultValues: { items: block.items },
  });
  const { fields, append, remove, move } = useFieldArray({ control, name: "items" });

  function onSubmit(values: Values) {
    setFormError(null);
    update.mutate(
      { data: values },
      {
        onSuccess: (saved) => {
          reset({ items: saved.items });
          afterSave();
        },
        // Ошибки элементов (loc с индексом) на поля не ложатся: показываем сообщение целиком.
        onError: (error) => setFormError(applyApiErrors(error, setError, [])),
      },
    );
  }

  return (
    <BlockForm
      title="Услуги"
      onSubmit={handleSubmit(onSubmit)}
      formError={formError}
      pending={update.isPending}
    >
      {fields.length === 0 && <p className="text-sm text-muted-foreground">Услуг пока нет.</p>}
      {fields.map((field, index) => {
        const itemErrors = errors.items?.[index];
        const id = `service-${field.id}`;
        return (
          <ListItem
            key={field.id}
            title={`Услуга ${index + 1}`}
            controls={
              <ListControls
                index={index}
                count={fields.length}
                noun="услугу"
                onMoveUp={() => move(index, index - 1)}
                onMoveDown={() => move(index, index + 1)}
                onRemove={() => remove(index)}
              />
            }
          >
            <TextField
              id={`${id}-title`}
              label="Название"
              error={itemErrors?.title?.message}
              {...register(`items.${index}.title`)}
            />
            <TextareaField
              id={`${id}-description`}
              label="Описание"
              rows={3}
              error={itemErrors?.description?.message}
              {...register(`items.${index}.description`)}
            />
            <div className="grid gap-4 sm:grid-cols-3">
              <TextField
                id={`${id}-duration`}
                label="Длительность, мин"
                type="number"
                inputMode="numeric"
                error={itemErrors?.duration_min?.message}
                {...register(`items.${index}.duration_min`, { valueAsNumber: true })}
              />
              <TextField
                id={`${id}-price`}
                label="Цена, ₽"
                type="number"
                inputMode="numeric"
                error={itemErrors?.price_rub?.message}
                {...register(`items.${index}.price_rub`, { valueAsNumber: true })}
              />
              <TextField
                id={`${id}-format`}
                label="Формат"
                error={itemErrors?.format?.message}
                {...register(`items.${index}.format`)}
              />
            </div>
          </ListItem>
        );
      })}
      {errors.items?.message && <p className="text-sm text-destructive">{errors.items.message}</p>}
      <div>
        <Button
          type="button"
          variant="outline"
          disabled={fields.length >= updateServicesBlockBodyItemsMax}
          onClick={() => append(EMPTY_SERVICE)}
        >
          Добавить услугу
        </Button>
      </div>
    </BlockForm>
  );
}
