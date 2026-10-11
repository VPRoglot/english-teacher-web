"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { useUpdateFamily } from "@/api/generated/endpoints/admin/admin";
import type { FamilyDetail } from "@/api/generated/model";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { applyApiErrors } from "@/lib/form-errors";

import { useRefreshFamily } from "./use-refresh-family";

const schema = z.object({
  name: z.string().trim().min(1, "Введите название").max(200, "Не более 200 символов"),
  tutor_comment: z.string().trim(),
});

type Values = z.infer<typeof schema>;

function EditFamilyForm({ family, onSaved }: { family: FamilyDetail; onSaved: () => void }) {
  const [formError, setFormError] = useState<string | null>(null);
  const refresh = useRefreshFamily(family.id);
  const update = useUpdateFamily();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { name: family.name, tutor_comment: family.tutor_comment ?? "" },
  });

  function onSubmit(values: Values) {
    setFormError(null);
    update.mutate(
      {
        familyId: family.id,
        data: { name: values.name, tutor_comment: values.tutor_comment || null },
      },
      {
        onSuccess: async () => {
          toast.success("Семья сохранена");
          onSaved();
          await refresh();
        },
        onError: (error) => setFormError(applyApiErrors(error, setError, ["name", "tutor_comment"])),
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
        <Label htmlFor="edit-family-name">Название</Label>
        <Input
          id="edit-family-name"
          aria-invalid={errors.name ? true : undefined}
          {...register("name")}
        />
        {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="edit-family-comment">Комментарий</Label>
        <Textarea
          id="edit-family-comment"
          aria-invalid={errors.tutor_comment ? true : undefined}
          {...register("tutor_comment")}
        />
        {errors.tutor_comment && (
          <p className="text-sm text-destructive">{errors.tutor_comment.message}</p>
        )}
      </div>
      <Button type="submit" disabled={update.isPending}>
        {update.isPending ? "Сохраняем…" : "Сохранить"}
      </Button>
    </form>
  );
}

export function EditFamilyDialog({ family }: { family: FamilyDetail }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button type="button" variant="outline" onClick={() => setOpen(true)}>
        Изменить семью
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Изменить семью</DialogTitle>
          </DialogHeader>
          <EditFamilyForm family={family} onSaved={() => setOpen(false)} />
        </DialogContent>
      </Dialog>
    </>
  );
}
