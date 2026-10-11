"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useGetPasswordReset, useResetPassword } from "@/api/generated/endpoints/auth/auth";
import { PasswordField } from "@/components/password-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api-fetch";
import { applyApiErrors, applyPasswordPolicyError, errorMessage } from "@/lib/form-errors";

const schema = z
  .object({
    password: z.string().min(1, "Введите пароль").max(128, "Пароль слишком длинный"),
    repeat: z.string().min(1, "Повторите пароль"),
  })
  .refine((values) => values.password === values.repeat, {
    message: "Пароли не совпадают",
    path: ["repeat"],
  });

type ResetValues = z.infer<typeof schema>;

function Notice({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle className="text-xl">{title}</CardTitle>
      </CardHeader>
      {children && <CardContent>{children}</CardContent>}
    </Card>
  );
}

export function ResetPassword() {
  const { token } = useParams<{ token: string }>();
  const info = useGetPasswordReset(token, { query: { meta: { skipAuthRedirect: true }, retry: false } });

  if (info.isPending) return null;
  if (info.error instanceof ApiError && info.error.code === "reset_invalid") {
    return (
      <Notice title="Ссылка недействительна">
        <p className="text-sm text-muted-foreground">
          Ссылка для смены пароля недействительна или устарела. Попросите репетитора прислать новую.
        </p>
      </Notice>
    );
  }
  if (info.isError) {
    return (
      <Notice title="Не удалось открыть ссылку">
        <p className="text-sm text-muted-foreground">{errorMessage(info.error)}</p>
      </Notice>
    );
  }
  return <ResetForm token={token} login={info.data.login} />;
}

function ResetForm({ token, login }: { token: string; login: string }) {
  const [formError, setFormError] = useState<string | null>(null);
  const reset = useResetPassword();

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<ResetValues>({
    resolver: zodResolver(schema),
    defaultValues: { password: "", repeat: "" },
  });

  function onSubmit(values: ResetValues) {
    setFormError(null);
    reset.mutate(
      { token, data: { password: values.password } },
      {
        onError: (error) => {
          if (applyPasswordPolicyError(error, setError)) return;
          setFormError(applyApiErrors(error, setError, ["password"]));
        },
      },
    );
  }

  if (reset.isSuccess) {
    return (
      <Notice title="Пароль изменён">
        <Link href="/login" className={buttonVariants()}>
          Войти
        </Link>
      </Notice>
    );
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle className="text-xl">Новый пароль для {login}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
          {formError && (
            <Alert variant="destructive">
              <AlertDescription>{formError}</AlertDescription>
            </Alert>
          )}
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
            <Label htmlFor="repeat">Повторите пароль</Label>
            <PasswordField
              id="repeat"
              autoComplete="new-password"
              aria-invalid={errors.repeat ? true : undefined}
              {...register("repeat")}
            />
            {errors.repeat && <p className="text-sm text-destructive">{errors.repeat.message}</p>}
          </div>
          <Button type="submit" disabled={reset.isPending}>
            {reset.isPending ? "Сохраняем…" : "Сменить пароль"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
