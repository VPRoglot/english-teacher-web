"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import type { z } from "zod";

import { useUpdateFaqBlock } from "@/api/generated/endpoints/admin/admin";
import type { FaqBlock } from "@/api/generated/model";
import { UpdateFaqBlockBody, updateFaqBlockBodyItemsMax } from "@/api/generated/zod/admin/admin";
import { Button } from "@/components/ui/button";
import { applyApiErrors } from "@/lib/form-errors";

import { ListControls, ListItem } from "./list-controls";
import { BlockForm, TextareaField, TextField, useAfterSave, zodOptions } from "./site-form";

type Values = z.infer<typeof UpdateFaqBlockBody>;

export function FaqEditor({ block }: { block: FaqBlock }) {
  const [formError, setFormError] = useState<string | null>(null);
  const update = useUpdateFaqBlock();
  const afterSave = useAfterSave();
  const {
    register,
    control,
    handleSubmit,
    setError,
    reset,
    formState: { errors },
  } = useForm<Values>({
    resolver: zodResolver(UpdateFaqBlockBody, zodOptions),
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
        onError: (error) => setFormError(applyApiErrors(error, setError, [])),
      },
    );
  }

  return (
    <BlockForm
      title="Вопросы и ответы"
      onSubmit={handleSubmit(onSubmit)}
      formError={formError}
      pending={update.isPending}
    >
      {fields.length === 0 && <p className="text-sm text-muted-foreground">Вопросов пока нет.</p>}
      {fields.map((field, index) => {
        const itemErrors = errors.items?.[index];
        const id = `faq-${field.id}`;
        return (
          <ListItem
            key={field.id}
            title={`Вопрос ${index + 1}`}
            controls={
              <ListControls
                index={index}
                count={fields.length}
                noun="вопрос"
                onMoveUp={() => move(index, index - 1)}
                onMoveDown={() => move(index, index + 1)}
                onRemove={() => remove(index)}
              />
            }
          >
            <TextField
              id={`${id}-question`}
              label="Вопрос"
              error={itemErrors?.question?.message}
              {...register(`items.${index}.question`)}
            />
            <TextareaField
              id={`${id}-answer`}
              label="Ответ"
              rows={4}
              error={itemErrors?.answer?.message}
              {...register(`items.${index}.answer`)}
            />
          </ListItem>
        );
      })}
      {errors.items?.message && <p className="text-sm text-destructive">{errors.items.message}</p>}
      <div>
        <Button
          type="button"
          variant="outline"
          disabled={fields.length >= updateFaqBlockBodyItemsMax}
          onClick={() => append({ question: "", answer: "" })}
        >
          Добавить вопрос
        </Button>
      </div>
    </BlockForm>
  );
}
