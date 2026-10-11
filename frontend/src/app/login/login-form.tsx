"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { getGetMeQueryKey, useGetMe, useLogin } from "@/api/generated/endpoints/auth/auth";
import { PasswordField } from "@/components/password-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api-fetch";
import { homeFor, safeNext } from "@/lib/auth";
import { errorMessage } from "@/lib/form-errors";

const schema = z.object({
  login: z.string().min(1, "Введите email или логин"),
  password: z.string().min(1, "Введите пароль").max(128, "Пароль слишком длинный"),
});

type LoginValues = z.infer<typeof schema>;

function loginErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "invalid_credentials") return "Неверный логин или пароль";
    const retryAfter = error.details.retry_after;
    if (error.code === "rate_limited" && typeof retryAfter === "number") {
      return `Слишком много попыток. Попробуйте через ${Math.ceil(retryAfter / 60)} мин.`;
    }
  }
  return errorMessage(error);
}

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [formError, setFormError] = useState<string | null>(null);

  const queryClient = useQueryClient();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<LoginValues>({
    resolver: zodResolver(schema),
    defaultValues: { login: "", password: "" },
  });

  // Проба сессии: 401 здесь — норма (не залогинен), глобальный редирект на /login не нужен.
  const me = useGetMe({ query: { meta: { skipAuthRedirect: true }, retry: false } });
  const login = useLogin();

  const signedInRole = me.data?.role;
  // Уводит только уже вошедшего посетителя. После входа /me в кэше заполняет onSuccess,
  // и навигацию (с учётом next) делает он же — эффект не должен перебить её главной роли.
  const justSignedIn = login.isSuccess;
  useEffect(() => {
    if (signedInRole && !justSignedIn) router.replace(homeFor(signedInRole));
  }, [signedInRole, justSignedIn, router]);

  function onSubmit(values: LoginValues) {
    setFormError(null);
    login.mutate(
      { data: values },
      {
        onSuccess: (user) => {
          // Страница входа остаётся скрытой в <Activity>: логин и пароль в ней не храним.
          reset({ login: "", password: "" });
          // Оболочки читают /me из кэша — там должен быть пользователь, а не 401 от пробы.
          queryClient.setQueryData(getGetMeQueryKey(), user);
          router.replace(safeNext(searchParams.get("next")) ?? homeFor(user.role));
        },
        onError: (error) => setFormError(loginErrorMessage(error)),
      },
    );
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle className="text-xl">Вход</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
          {formError && (
            <Alert variant="destructive">
              <AlertDescription>{formError}</AlertDescription>
            </Alert>
          )}
          <div className="flex flex-col gap-2">
            <Label htmlFor="login">Email или логин</Label>
            <Input
              id="login"
              autoComplete="username"
              aria-invalid={errors.login ? true : undefined}
              {...register("login")}
            />
            {errors.login && <p className="text-sm text-destructive">{errors.login.message}</p>}
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="password">Пароль</Label>
            <PasswordField
              id="password"
              autoComplete="current-password"
              aria-invalid={errors.password ? true : undefined}
              {...register("password")}
            />
            {errors.password && (
              <p className="text-sm text-destructive">{errors.password.message}</p>
            )}
          </div>
          <Button type="submit" disabled={login.isPending}>
            {login.isPending ? "Входим…" : "Войти"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
