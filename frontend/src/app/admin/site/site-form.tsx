"use client";

import { useQueryClient } from "@tanstack/react-query";
import type { ComponentProps, FormEventHandler, ReactNode } from "react";
import { toast } from "sonner";
import { z } from "zod";

import { getGetSiteBlocksQueryKey } from "@/api/generated/endpoints/admin/admin";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const SUCCESS_MESSAGE = "Сохранено. Сайт обновится в течение минуты";

const russian = z.locales.ru().localeError;

/**
 * Тексты ошибок клиентской проверки по-русски. Схемы сгенерированы из OpenAPI и без своих
 * сообщений, поэтому самые частые случаи (пустое поле, длина, email) переопределены здесь.
 */
export const zodOptions = {
  error: (issue: z.core.$ZodRawIssue) => {
    if (issue.code === "too_small" && issue.origin === "string" && issue.minimum === 1) {
      return "Заполните поле";
    }
    if (issue.code === "too_big" && issue.origin === "string") {
      return `Не более ${String(issue.maximum)} символов`;
    }
    if (issue.code === "invalid_format" && issue.format === "email") return "Некорректный email";
    return russian(issue);
  },
};

/** После успешного сохранения блока: уведомление и обновление данных редактора. */
export function useAfterSave(): () => void {
  const queryClient = useQueryClient();
  return () => {
    toast.success(SUCCESS_MESSAGE);
    void queryClient.invalidateQueries({ queryKey: getGetSiteBlocksQueryKey() });
  };
}

/** Карточка блока с формой, общей ошибкой и кнопкой «Сохранить». */
export function BlockForm({
  title,
  onSubmit,
  formError,
  pending,
  children,
}: {
  title: string;
  onSubmit: FormEventHandler<HTMLFormElement>;
  formError: string | null;
  pending: boolean;
  children: ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
          {formError && (
            <Alert variant="destructive">
              <AlertDescription>{formError}</AlertDescription>
            </Alert>
          )}
          {children}
          <div>
            <Button type="submit" disabled={pending}>
              {pending ? "Сохраняем…" : "Сохранить"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

/** Подпись, поле ввода и текст ошибки под ним. */
export function TextField({
  id,
  label,
  error,
  ...inputProps
}: { label: string; error?: string } & ComponentProps<typeof Input> & { id: string }) {
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} aria-invalid={error ? true : undefined} {...inputProps} />
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
