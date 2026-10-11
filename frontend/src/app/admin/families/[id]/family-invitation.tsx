"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { useCreateFamilyInvitation } from "@/api/generated/endpoints/admin/admin";
import type { FamilyDetail, LinkResponse } from "@/api/generated/model";
import { CopyLinkCard } from "@/components/copy-link-card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { applyApiErrors } from "@/lib/form-errors";
import { formatMoscow } from "@/lib/format";

import { useRefreshFamily } from "./use-refresh-family";

type Values = { prefill_full_name: string; prefill_phone: string };

export function FamilyInvitation({ family }: { family: FamilyDetail }) {
  const [link, setLink] = useState<LinkResponse | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const refresh = useRefreshFamily(family.id);
  const createInvitation = useCreateFamilyInvitation();
  const { register, handleSubmit, setError, reset } = useForm<Values>({
    defaultValues: { prefill_full_name: "", prefill_phone: "" },
  });
  const archived = family.archived_at !== null;

  function onSubmit(values: Values) {
    setFormError(null);
    createInvitation.mutate(
      {
        familyId: family.id,
        data: {
          prefill_full_name: values.prefill_full_name.trim() || null,
          prefill_phone: values.prefill_phone.trim() || null,
        },
      },
      {
        onSuccess: async (created) => {
          setLink(created);
          reset();
          toast.success("Ссылка-приглашение создана");
          await refresh();
        },
        onError: (error) =>
          setFormError(applyApiErrors(error, setError, ["prefill_full_name", "prefill_phone"])),
      },
    );
  }

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold">Приглашение</h2>
      {family.pending_invitation && (
        <div className="flex flex-col gap-1 text-sm">
          <p>{`Ссылка отправлена, действует до ${formatMoscow(family.pending_invitation.expires_at)}`}</p>
          <p className="text-muted-foreground">
            Новая ссылка отменит прежнюю: по старой родитель уже не сможет зарегистрироваться.
          </p>
        </div>
      )}
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
        {formError && (
          <Alert variant="destructive">
            <AlertDescription>{formError}</AlertDescription>
          </Alert>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-2">
            <Label htmlFor="invite-name">ФИО</Label>
            <Input
              id="invite-name"
              placeholder="Необязательно: подставится в форму родителя"
              {...register("prefill_full_name")}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="invite-phone">Телефон</Label>
            <Input id="invite-phone" placeholder="Необязательно" {...register("prefill_phone")} />
          </div>
        </div>
        <Button
          type="submit"
          className="self-start"
          disabled={archived || createInvitation.isPending}
        >
          Создать ссылку-приглашение
        </Button>
      </form>
      {link && <CopyLinkCard url={link.url} expiresAt={link.expires_at} title="Ссылка-приглашение" />}
    </section>
  );
}
