"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { useAcceptInvitation, useGetInvitation } from "@/api/generated/endpoints/auth/auth";
import type { InvitationInfo } from "@/api/generated/model";
import { PasswordField } from "@/components/password-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api-fetch";
import { applyApiErrors, applyPasswordPolicyError, errorMessage } from "@/lib/form-errors";

// Совпадает с pattern в AcceptInvitationRequest (backend).
const PHONE_PATTERN = /^\+?[0-9\s()-]{6,32}$/;

const schema = z
  .object({
    full_name: z.string().trim().min(1, "Введите ФИО").max(200, "Не более 200 символов"),
    phone: z.string().trim().regex(PHONE_PATTERN, "Введите корректный телефон"),
    email: z.string().trim().min(1, "Введите email").max(254, "Не более 254 символов"),
    password: z.string().min(1, "Введите пароль").max(128, "Пароль слишком длинный"),
    repeat: z.string().min(1, "Повторите пароль"),
    consent: z.boolean().refine((value) => value, {
      message: "Необходимо согласие на обработку персональных данных",
    }),
  })
  .refine((values) => values.password === values.repeat, {
    message: "Пароли не совпадают",
    path: ["repeat"],
  });

type AcceptValues = z.infer<typeof schema>;

const API_FIELDS = ["email", "password", "full_name", "phone", "consent"] as const;

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

export function AcceptInvitation() {
  const { token } = useParams<{ token: string }>();
  const invitation = useGetInvitation(token, {
    query: { meta: { skipAuthRedirect: true }, retry: false },
  });

  if (invitation.isPending) return null;
  if (invitation.error instanceof ApiError && invitation.error.code === "invitation_invalid") {
    return (
      <Notice title="Ссылка недействительна">
        <p className="text-sm text-muted-foreground">
          Ссылка недействительна или устарела. Попросите репетитора прислать новую.
        </p>
      </Notice>
    );
  }
  if (invitation.isError) {
    return (
      <Notice title="Не удалось открыть приглашение">
        <p className="text-sm text-muted-foreground">{errorMessage(invitation.error)}</p>
      </Notice>
    );
  }
  return <InvitationForm token={token} invitation={invitation.data} />;
}

function InvitationForm({ token, invitation }: { token: string; invitation: InvitationInfo }) {
  const router = useRouter();
  const [formError, setFormError] = useState<string | null>(null);
  const accept = useAcceptInvitation();

  const {
    register,
    control,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<AcceptValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      full_name: invitation.prefill_full_name ?? "",
      phone: invitation.prefill_phone ?? "",
      email: "",
      password: "",
      repeat: "",
      consent: false,
    },
  });

  function onSubmit(values: AcceptValues) {
    setFormError(null);
    accept.mutate(
      {
        token,
        data: {
          email: values.email,
          password: values.password,
          full_name: values.full_name,
          phone: values.phone,
          consent: true,
        },
      },
      {
        onSuccess: () => router.replace("/cabinet"),
        onError: (error) => {
          if (applyPasswordPolicyError(error, setError)) return;
          setFormError(applyApiErrors(error, setError, API_FIELDS));
        },
      },
    );
  }

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle className="text-xl">Приглашение в семью «{invitation.family_name}»</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
          {formError && (
            <Alert variant="destructive">
              <AlertDescription>{formError}</AlertDescription>
            </Alert>
          )}
          <div className="flex flex-col gap-2">
            <Label htmlFor="full_name">ФИО</Label>
            <Input
              id="full_name"
              autoComplete="name"
              aria-invalid={errors.full_name ? true : undefined}
              {...register("full_name")}
            />
            {errors.full_name && (
              <p className="text-sm text-destructive">{errors.full_name.message}</p>
            )}
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="phone">Телефон</Label>
            <Input
              id="phone"
              type="tel"
              autoComplete="tel"
              aria-invalid={errors.phone ? true : undefined}
              {...register("phone")}
            />
            {errors.phone && <p className="text-sm text-destructive">{errors.phone.message}</p>}
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              aria-invalid={errors.email ? true : undefined}
              {...register("email")}
            />
            {errors.email && <p className="text-sm text-destructive">{errors.email.message}</p>}
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="password">Пароль</Label>
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
          <div className="flex flex-col gap-2">
            <div className="flex items-start gap-2">
              <Controller
                control={control}
                name="consent"
                render={({ field }) => (
                  <Checkbox
                    id="consent"
                    checked={field.value}
                    onCheckedChange={field.onChange}
                    onBlur={field.onBlur}
                    aria-invalid={errors.consent ? true : undefined}
                    className="mt-0.5"
                  />
                )}
              />
              <Label htmlFor="consent" className="leading-snug font-normal">
                <span>
                  Согласен на обработку{" "}
                  <a
                    href="/privacy"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline underline-offset-2"
                  >
                    персональных данных
                  </a>
                </span>
              </Label>
            </div>
            {errors.consent && (
              <p className="text-sm text-destructive">{errors.consent.message}</p>
            )}
          </div>
          <Button type="submit" disabled={accept.isPending}>
            {accept.isPending ? "Сохраняем…" : "Принять приглашение"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
