"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { useCreateFamily } from "@/api/generated/endpoints/admin/admin";
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
import { Textarea } from "@/components/ui/textarea";
import { applyApiErrors } from "@/lib/form-errors";

const schema = z.object({
  name: z.string().trim().min(1, "Введите название").max(200, "Не более 200 символов"),
  tutor_comment: z.string().trim(),
});

type Values = z.infer<typeof schema>;

function CreateFamilyForm({ onCreated }: { onCreated: () => void }) {
  const router = useRouter();
  const [formError, setFormError] = useState<string | null>(null);
  const create = useCreateFamily();
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", tutor_comment: "" },
  });

  function onSubmit(values: Values) {
    setFormError(null);
    create.mutate(
      { data: { name: values.name, tutor_comment: values.tutor_comment || null } },
      {
        onSuccess: (family) => {
          toast.success("Семья создана");
          // Прежний маршрут остаётся смонтированным (Activity): закрываем и очищаем форму до перехода.
          reset();
          onCreated();
          router.push(`/admin/families/${family.id}`);
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
        <Label htmlFor="family-name">Название</Label>
        <Input
          id="family-name"
          placeholder="Семья Ивановых"
          aria-invalid={errors.name ? true : undefined}
          {...register("name")}
        />
        {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="family-comment">Комментарий</Label>
        <Textarea
          id="family-comment"
          aria-invalid={errors.tutor_comment ? true : undefined}
          {...register("tutor_comment")}
        />
        {errors.tutor_comment && (
          <p className="text-sm text-destructive">{errors.tutor_comment.message}</p>
        )}
      </div>
      <Button type="submit" disabled={create.isPending}>
        {create.isPending ? "Создаём…" : "Создать"}
      </Button>
    </form>
  );
}

export function CreateFamilyDialog() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Новая семья</Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Новая семья</DialogTitle>
            <DialogDescription>Родителей и детей можно добавить на странице семьи.</DialogDescription>
          </DialogHeader>
          <CreateFamilyForm onCreated={() => setOpen(false)} />
        </DialogContent>
      </Dialog>
    </>
  );
}
