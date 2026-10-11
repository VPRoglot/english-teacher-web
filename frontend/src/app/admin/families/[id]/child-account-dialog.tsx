"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { useSetChildAccountAdmin } from "@/api/generated/endpoints/admin/admin";
import type { ChildDetail } from "@/api/generated/model";
import { PasswordField } from "@/components/password-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { applyApiErrors, applyPasswordPolicyError } from "@/lib/form-errors";

import { useRefreshFamily } from "./use-refresh-family";

const schema = z.object({
  username: z.string().trim().min(1, "Введите логин").max(64, "Логин слишком длинный"),
  password: z.string().min(6, "Минимум 6 символов").max(128, "Пароль слишком длинный"),
});

type Values = z.infer<typeof schema>;

function ChildAccountForm({
  familyId,
  child,
  onSaved,
}: {
  familyId: string;
  child: ChildDetail;
  onSaved: () => void;
}) {
  const [formError, setFormError] = useState<string | null>(null);
  const refresh = useRefreshFamily(familyId);
  const setAccount = useSetChildAccountAdmin();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { username: child.account?.username ?? "", password: "" },
  });

  function onSubmit(values: Values) {
    setFormError(null);
    setAccount.mutate(
      { childId: child.id, data: values },
      {
        onSuccess: async () => {
          toast.success("Логин сохранён");
          onSaved();
          await refresh();
        },
        onError: (error) => {
          if (applyPasswordPolicyError(error, setError)) return;
          setFormError(applyApiErrors(error, setError, ["username", "password"]));
        },
      },
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
      {formError && (
        <Alert variant="destructive">
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      )}
      <div className="flex flex-col gap-2">
        <Label htmlFor={`account-username-${child.id}`}>Логин</Label>
        <Input
          id={`account-username-${child.id}`}
          autoComplete="off"
          aria-invalid={errors.username ? true : undefined}
          {...register("username")}
        />
        {errors.username && <p className="text-sm text-destructive">{errors.username.message}</p>}
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor={`account-password-${child.id}`}>Пароль</Label>
        <PasswordField
          id={`account-password-${child.id}`}
          autoComplete="new-password"
          aria-invalid={errors.password ? true : undefined}
          {...register("password")}
        />
        {errors.password && <p className="text-sm text-destructive">{errors.password.message}</p>}
      </div>
      <Button type="submit" disabled={setAccount.isPending}>
        {setAccount.isPending ? "Сохраняем…" : "Сохранить"}
      </Button>
    </form>
  );
}

/** Логин и пароль ребёнка: создаёт учётку или меняет существующую. */
export function ChildAccountDialog({
  familyId,
  child,
}: {
  familyId: string;
  child: ChildDetail;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)}>
        Логин и пароль
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Логин и пароль: {child.full_name}</DialogTitle>
            <DialogDescription>
              {child.account
                ? "Новый пароль заменит прежний."
                : "Ребёнок войдёт в кабинет с этим логином и паролем."}
            </DialogDescription>
          </DialogHeader>
          <ChildAccountForm familyId={familyId} child={child} onSaved={() => setOpen(false)} />
        </DialogContent>
      </Dialog>
    </>
  );
}
