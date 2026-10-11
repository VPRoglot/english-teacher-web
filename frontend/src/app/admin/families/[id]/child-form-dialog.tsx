"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { useAddChild, useUpdateChild } from "@/api/generated/endpoints/admin/admin";
import type { ChildCreate, ChildDetail } from "@/api/generated/model";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { applyApiErrors } from "@/lib/form-errors";

import { useRefreshFamily } from "./use-refresh-family";

const NO_LEVEL = "none";
const LEVEL_LABELS = { [NO_LEVEL]: "не указан", A1: "A1", A2: "A2", B1: "B1", B2: "B2", C1: "C1" };

const schema = z.object({
  full_name: z.string().trim().min(1, "Введите имя").max(200, "Не более 200 символов"),
  birth_year: z.string().trim().regex(/^(\d{4})?$/, "Введите год из четырёх цифр"),
  english_level: z.enum([NO_LEVEL, "A1", "A2", "B1", "B2", "C1"]),
  default_meeting_url: z.string().trim(),
});

type Values = z.infer<typeof schema>;

function toPayload(values: Values): ChildCreate {
  return {
    full_name: values.full_name,
    birth_year: values.birth_year ? Number(values.birth_year) : null,
    english_level: values.english_level === NO_LEVEL ? null : values.english_level,
    default_meeting_url: values.default_meeting_url || null,
  };
}

function ChildForm({
  familyId,
  child,
  onSaved,
}: {
  familyId: string;
  child?: ChildDetail;
  onSaved: () => void;
}) {
  const [formError, setFormError] = useState<string | null>(null);
  const refresh = useRefreshFamily(familyId);
  const addChild = useAddChild();
  const updateChild = useUpdateChild();
  const pending = addChild.isPending || updateChild.isPending;
  const idPrefix = `child-${child?.id ?? "new"}`;

  const {
    register,
    control,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      full_name: child?.full_name ?? "",
      birth_year: child?.birth_year?.toString() ?? "",
      english_level: child?.english_level ?? NO_LEVEL,
      default_meeting_url: child?.default_meeting_url ?? "",
    },
  });

  function onSubmit(values: Values) {
    setFormError(null);
    const data = toPayload(values);
    const options = {
      onSuccess: async () => {
        toast.success(child ? "Изменения сохранены" : "Ребёнок добавлен");
        onSaved();
        await refresh();
      },
      onError: (error: unknown) =>
        setFormError(
          applyApiErrors(error, setError, [
            "full_name",
            "birth_year",
            "english_level",
            "default_meeting_url",
          ]),
        ),
    };
    if (child) updateChild.mutate({ childId: child.id, data }, options);
    else addChild.mutate({ familyId, data }, options);
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
      {formError && (
        <Alert variant="destructive">
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      )}
      <div className="flex flex-col gap-2">
        <Label htmlFor={`${idPrefix}-name`}>Имя</Label>
        <Input
          id={`${idPrefix}-name`}
          aria-invalid={errors.full_name ? true : undefined}
          {...register("full_name")}
        />
        {errors.full_name && <p className="text-sm text-destructive">{errors.full_name.message}</p>}
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor={`${idPrefix}-year`}>Год рождения</Label>
        <Input
          id={`${idPrefix}-year`}
          inputMode="numeric"
          placeholder="2015"
          aria-invalid={errors.birth_year ? true : undefined}
          {...register("birth_year")}
        />
        {errors.birth_year && <p className="text-sm text-destructive">{errors.birth_year.message}</p>}
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor={`${idPrefix}-level`}>Уровень английского</Label>
        <Controller
          name="english_level"
          control={control}
          render={({ field }) => (
            <Select
              items={LEVEL_LABELS}
              value={field.value}
              onValueChange={(value) => field.onChange(value ?? NO_LEVEL)}
            >
              <SelectTrigger id={`${idPrefix}-level`} onBlur={field.onBlur} className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(LEVEL_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        />
        {errors.english_level && (
          <p className="text-sm text-destructive">{errors.english_level.message}</p>
        )}
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor={`${idPrefix}-url`}>Ссылка на занятие</Label>
        <Input
          id={`${idPrefix}-url`}
          type="url"
          placeholder="https://"
          aria-invalid={errors.default_meeting_url ? true : undefined}
          {...register("default_meeting_url")}
        />
        {errors.default_meeting_url && (
          <p className="text-sm text-destructive">{errors.default_meeting_url.message}</p>
        )}
      </div>
      <Button type="submit" disabled={pending}>
        {pending ? "Сохраняем…" : "Сохранить"}
      </Button>
    </form>
  );
}

/** Добавление ребёнка (без `child`) или правка его данных. Кнопка-триггер входит в компонент. */
export function ChildFormDialog({ familyId, child }: { familyId: string; child?: ChildDetail }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        type="button"
        variant="outline"
        size={child ? "sm" : "default"}
        onClick={() => setOpen(true)}
      >
        {child ? "Изменить" : "Добавить ребёнка"}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{child ? `Изменить: ${child.full_name}` : "Добавить ребёнка"}</DialogTitle>
          </DialogHeader>
          <ChildForm familyId={familyId} child={child} onSaved={() => setOpen(false)} />
        </DialogContent>
      </Dialog>
    </>
  );
}
