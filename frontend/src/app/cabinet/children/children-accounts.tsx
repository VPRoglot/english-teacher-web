"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { useGetMe } from "@/api/generated/endpoints/auth/auth";
import {
  getListMyChildrenQueryKey,
  useListMyChildren,
  useSetMyChildAccount,
} from "@/api/generated/endpoints/cabinet/cabinet";
import type { CabinetChild } from "@/api/generated/model";
import { PasswordField } from "@/components/password-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { applyApiErrors, applyPasswordPolicyError, errorMessage } from "@/lib/form-errors";

const schema = z.object({
  username: z.string().trim().min(1, "Введите логин").max(64, "Логин слишком длинный"),
  password: z.string().min(6, "Минимум 6 символов").max(128, "Пароль слишком длинный"),
});

type AccountValues = z.infer<typeof schema>;

export function ChildrenAccounts() {
  const router = useRouter();
  const me = useGetMe();
  const role = me.data?.role;
  const children = useListMyChildren({ query: { enabled: role === "parent" } });

  useEffect(() => {
    if (role === "child") router.replace("/cabinet");
  }, [role, router]);

  if (role !== "parent") return null;
  if (children.error) {
    return <p className="text-sm text-muted-foreground">{errorMessage(children.error)}</p>;
  }
  if (!children.data) return null;

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">Дети</h1>
      {children.data.length === 0 ? (
        <p className="text-sm text-muted-foreground">Детей пока нет.</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {children.data.map((child) => (
            <ChildAccountCard key={child.id} child={child} />
          ))}
        </div>
      )}
    </>
  );
}

function ChildAccountCard({ child }: { child: CabinetChild }) {
  const queryClient = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);
  const setAccount = useSetMyChildAccount();
  const usernameId = `username-${child.id}`;
  const passwordId = `password-${child.id}`;

  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors },
  } = useForm<AccountValues>({
    resolver: zodResolver(schema),
    defaultValues: { username: child.username ?? "", password: "" },
  });

  function onSubmit(values: AccountValues) {
    setFormError(null);
    setAccount.mutate(
      { childId: child.id, data: values },
      {
        onSuccess: async (saved) => {
          reset({ username: saved.username ?? values.username, password: "" });
          toast.success("Логин сохранён");
          await queryClient.invalidateQueries({ queryKey: getListMyChildrenQueryKey() });
        },
        onError: (error) => {
          if (applyPasswordPolicyError(error, setError)) return;
          setFormError(applyApiErrors(error, setError, ["username", "password"]));
        },
      },
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{child.full_name}</CardTitle>
        <p className="text-sm text-muted-foreground">
          {child.username ? `Логин: ${child.username}` : "Логин не выдан"}
        </p>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
          {formError && (
            <Alert variant="destructive">
              <AlertDescription>{formError}</AlertDescription>
            </Alert>
          )}
          <div className="flex flex-col gap-2">
            <Label htmlFor={usernameId}>Логин</Label>
            <Input
              id={usernameId}
              autoComplete="off"
              aria-invalid={errors.username ? true : undefined}
              {...register("username")}
            />
            {errors.username && (
              <p className="text-sm text-destructive">{errors.username.message}</p>
            )}
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor={passwordId}>Пароль</Label>
            <PasswordField
              id={passwordId}
              autoComplete="new-password"
              aria-invalid={errors.password ? true : undefined}
              {...register("password")}
            />
            {errors.password && (
              <p className="text-sm text-destructive">{errors.password.message}</p>
            )}
          </div>
          <Button type="submit" disabled={setAccount.isPending}>
            {setAccount.isPending ? "Сохраняем…" : "Сохранить"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
