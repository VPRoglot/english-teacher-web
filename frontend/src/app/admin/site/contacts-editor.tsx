"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useUpdateContactsBlock } from "@/api/generated/endpoints/admin/admin";
import type { ContactsBlock } from "@/api/generated/model";
import { UpdateContactsBlockBody } from "@/api/generated/zod/admin/admin";
import { applyApiErrors } from "@/lib/form-errors";

import { BlockForm, TextField, useAfterSave, zodOptions } from "./site-form";

const FIELDS = ["email", "phone", "telegram", "whatsapp", "working_hours_text"] as const;

function blankToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

// Поля формы — строки. Пустое значение превращается в null до проверки сгенерированной схемой:
// backend так же хранит пустые контакты, а `email` и `working_hours_text` в схеме не принимают "".
const schema = z
  .object({
    email: z.string(),
    phone: z.string(),
    telegram: z.string(),
    whatsapp: z.string(),
    working_hours_text: z.string(),
  })
  .transform((values): z.input<typeof UpdateContactsBlockBody> => ({
    email: blankToNull(values.email),
    phone: blankToNull(values.phone),
    telegram: blankToNull(values.telegram),
    whatsapp: blankToNull(values.whatsapp),
    working_hours_text: blankToNull(values.working_hours_text),
  }))
  .pipe(UpdateContactsBlockBody);

type FormValues = z.input<typeof schema>;
type Output = z.output<typeof schema>;

function toValues(block: ContactsBlock): FormValues {
  return {
    email: block.email ?? "",
    phone: block.phone ?? "",
    telegram: block.telegram ?? "",
    whatsapp: block.whatsapp ?? "",
    working_hours_text: block.working_hours_text ?? "",
  };
}

export function ContactsEditor({ block }: { block: ContactsBlock }) {
  const [formError, setFormError] = useState<string | null>(null);
  const update = useUpdateContactsBlock();
  const afterSave = useAfterSave();
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors },
  } = useForm<FormValues, unknown, Output>({
    resolver: zodResolver(schema, zodOptions),
    defaultValues: toValues(block),
  });

  function onSubmit(values: Output) {
    setFormError(null);
    update.mutate(
      { data: values },
      {
        onSuccess: (saved) => {
          // Сервер возвращает нормализованные значения — показываем именно их.
          reset(toValues(saved));
          afterSave();
        },
        onError: (error) => setFormError(applyApiErrors(error, setError, FIELDS)),
      },
    );
  }

  return (
    <BlockForm
      title="Контакты"
      onSubmit={handleSubmit(onSubmit)}
      formError={formError}
      pending={update.isPending}
    >
      <TextField
        id="contacts-email"
        label="Email"
        type="email"
        error={errors.email?.message}
        {...register("email")}
      />
      <TextField
        id="contacts-phone"
        label="Телефон"
        type="tel"
        error={errors.phone?.message}
        {...register("phone")}
      />
      <TextField
        id="contacts-telegram"
        label="Telegram"
        placeholder="@username"
        error={errors.telegram?.message}
        {...register("telegram")}
      />
      <TextField
        id="contacts-whatsapp"
        label="WhatsApp"
        error={errors.whatsapp?.message}
        {...register("whatsapp")}
      />
      <TextField
        id="contacts-hours"
        label="Часы работы"
        placeholder="Пн–Пт 10:00–20:00"
        error={errors.working_hours_text?.message}
        {...register("working_hours_text")}
      />
    </BlockForm>
  );
}
