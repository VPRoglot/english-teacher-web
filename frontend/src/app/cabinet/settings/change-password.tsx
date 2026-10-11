"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { useChangePassword } from "@/api/generated/endpoints/auth/auth";
import { PasswordField } from "@/components/password-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { applyApiErrors, applyPasswordPolicyError } from "@/lib/form-errors";

// `password` — новый пароль: под этим именем политика пароля из API ложится на поле.
const schema = z
  .object({
    current_password: z.string().min(1, "Введите текущий пароль").max(128, "Пароль слишком длинный"),
    password: z.string().min(1, "Введите новый пароль").max(128, "Пароль слишком длинный"),
    repeat: z.string().min(1, "Повторите новый пароль"),
  })
  .refine((values) => values.password === values.repeat, {
    message: "Пароли не совпадают",
    path: ["repeat"],
  });

type PasswordValues = z.infer<typeof schema>;

const EMPTY: PasswordValues = { current_password: "", password: "", repeat: "" };

export function ChangePassword() {
  const [formError, setFormError] = useState<string | null>(null);
  const change = useChangePassword();

  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors },
  } = useForm<PasswordValues>({ resolver: zodResolver(schema), defaultValues: EMPTY });

  function onSubmit(values: PasswordValues) {
    setFormError(null);
    change.mutate(
      { data: { current_password: values.current_password, new_password: values.password } },
      {
        onSuccess: () => {
          reset(EMPTY);
          toast.success("Пароль изменён");
        },
        onError: (error) => {
          if (applyPasswordPolicyError(error, setError)) return;
          setFormError(applyApiErrors(error, setError, ["current_password", "password"]));
        },
      },
    );
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle className="text-xl">Смена пароля</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
          {formError && (
            <Alert variant="destructive">
              <AlertDescription>{formError}</AlertDescription>
            </Alert>
          )}
          <div className="flex flex-col gap-2">
            <Label htmlFor="current_password">Текущий пароль</Label>
            <PasswordField
              id="current_password"
              autoComplete="current-password"
              aria-invalid={errors.current_password ? true : undefined}
              {...register("current_password")}
            />
            {errors.current_password && (
              <p className="text-sm text-destructive">{errors.current_password.message}</p>
            )}
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="password">Новый пароль</Label>
            <PasswordField
              id="password"
              autoComplete="new-password"
              aria-invalid={errors.password ? true : undefined}
              {...register("password")}
            />
            {errors.password && (
              <p className="text-sm text-destructive">{errors.password.message}</p>
            )}
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="repeat">Повторите новый пароль</Label>
            <PasswordField
              id="repeat"
              autoComplete="new-password"
              aria-invalid={errors.repeat ? true : undefined}
              {...register("repeat")}
            />
            {errors.repeat && <p className="text-sm text-destructive">{errors.repeat.message}</p>}
          </div>
          <Button type="submit" disabled={change.isPending}>
            {change.isPending ? "Сохраняем…" : "Сменить пароль"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
