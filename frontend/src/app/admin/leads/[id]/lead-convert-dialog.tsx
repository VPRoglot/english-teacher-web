"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useState } from "react";
import { Controller, useForm, type Path, type UseFormSetError } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { useConvertLead } from "@/api/generated/endpoints/admin/admin";
import type { LeadConvert, LeadConverted, LeadDetail } from "@/api/generated/model";
import { ConvertLeadBody } from "@/api/generated/zod/admin/admin";
import { zodOptions } from "@/app/admin/site/site-form";
import { CopyLinkCard } from "@/components/copy-link-card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError } from "@/lib/api-fetch";
import { errorMessage } from "@/lib/form-errors";

import { useRefreshLead } from "./use-refresh-lead";

const NO_LEVEL = "none";
const LEVEL_LABELS = { [NO_LEVEL]: "не указан", A1: "A1", A2: "A2", B1: "B1", B2: "B2", C1: "C1" };

const CONVERT_HINT = "Доступно после назначения пробного занятия";

const child = ConvertLeadBody.shape.child.shape;
const parent = ConvertLeadBody.shape.parent.shape;

// Поля формы — строки; пробелы по краям отбрасываются до проверки по схеме API.
const schema = z.object({
  family_name: z.string().trim().pipe(ConvertLeadBody.shape.family_name),
  child: z.object({
    full_name: z.string().trim().pipe(child.full_name),
    birth_year: z.string().trim().regex(/^(\d{4})?$/, "Введите год из четырёх цифр"),
    english_level: z.enum([NO_LEVEL, "A1", "A2", "B1", "B2", "C1"]),
    default_meeting_url: z
      .string()
      .trim()
      .refine((value) => value === "" || URL.canParse(value), "Введите ссылку целиком, с https://"),
  }),
  parent: z.object({
    full_name: z.string().trim().pipe(parent.full_name),
    phone: z.string().trim().min(1).pipe(parent.phone),
  }),
});

type Values = z.input<typeof schema>;
type Parsed = z.output<typeof schema>;

const FIELDS = [
  "family_name",
  "child.full_name",
  "child.birth_year",
  "child.english_level",
  "child.default_meeting_url",
  "parent.full_name",
  "parent.phone",
] as const satisfies readonly Path<Values>[];

function toPayload(values: Parsed): LeadConvert {
  const level = values.child.english_level;
  return {
    family_name: values.family_name,
    child: {
      full_name: values.child.full_name,
      birth_year: values.child.birth_year ? Number(values.child.birth_year) : null,
      english_level: level === NO_LEVEL ? null : level,
      default_meeting_url: values.child.default_meeting_url || null,
    },
    parent: { full_name: values.parent.full_name, phone: values.parent.phone },
  };
}

/** 422 раскладывается по полям вложенной формы (`body.child.full_name` → `child.full_name`). */
function applyConvertErrors(error: unknown, setError: UseFormSetError<Values>): string | null {
  if (!(error instanceof ApiError)) return errorMessage(error);
  const issues = error.details.fields;
  if (!Array.isArray(issues) || issues.length === 0) return error.message;

  let unmapped = false;
  for (const issue of issues as { loc?: unknown; message?: unknown }[]) {
    const path = Array.isArray(issue.loc) ? issue.loc.slice(1).join(".") : "";
    if ((FIELDS as readonly string[]).includes(path) && typeof issue.message === "string") {
      setError(path as Path<Values>, { message: issue.message });
    } else {
      unmapped = true;
    }
  }
  return unmapped ? error.message : null;
}

function FieldError({ message }: { message?: string }) {
  return message ? <p className="text-sm text-destructive">{message}</p> : null;
}

function ConvertForm({
  lead,
  onConverted,
  onCancel,
}: {
  lead: LeadDetail;
  onConverted: (result: LeadConverted) => void;
  onCancel: () => void;
}) {
  const [formError, setFormError] = useState<string | null>(null);
  const refresh = useRefreshLead(lead.id);
  const convert = useConvertLead();
  const {
    register,
    control,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<Values, unknown, Parsed>({
    resolver: zodResolver(schema, zodOptions),
    defaultValues: {
      family_name: `Семья ${lead.child_name}`,
      child: { full_name: lead.child_name, birth_year: "", english_level: NO_LEVEL, default_meeting_url: "" },
      parent: { full_name: lead.parent_name, phone: lead.phone },
    },
  });

  function onSubmit(values: Parsed) {
    setFormError(null);
    convert.mutate(
      { leadId: lead.id, data: toPayload(values) },
      {
        onSuccess: (result) => {
          toast.success("Заявка преобразована в семью");
          onConverted(result);
          void refresh();
        },
        onError: (error) => {
          setFormError(applyConvertErrors(error, setError));
          // Статус мог измениться в другой вкладке: показываем актуальное состояние.
          if (error instanceof ApiError && error.status === 409) void refresh();
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
        <Label htmlFor="convert-family">Семья</Label>
        <Input
          id="convert-family"
          aria-invalid={errors.family_name ? true : undefined}
          {...register("family_name")}
        />
        <FieldError message={errors.family_name?.message} />
      </div>

      <fieldset className="flex flex-col gap-4">
        <legend className="mb-2 text-sm font-medium">Ребёнок</legend>
        <div className="flex flex-col gap-2">
          <Label htmlFor="convert-child-name">Имя ребёнка</Label>
          <Input
            id="convert-child-name"
            aria-invalid={errors.child?.full_name ? true : undefined}
            {...register("child.full_name")}
          />
          <FieldError message={errors.child?.full_name?.message} />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-2">
            <Label htmlFor="convert-child-year">Год рождения</Label>
            <Input
              id="convert-child-year"
              inputMode="numeric"
              placeholder="2015"
              aria-invalid={errors.child?.birth_year ? true : undefined}
              {...register("child.birth_year")}
            />
            <FieldError message={errors.child?.birth_year?.message} />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="convert-child-level">Уровень английского</Label>
            <Controller
              name="child.english_level"
              control={control}
              render={({ field }) => (
                <Select
                  items={LEVEL_LABELS}
                  value={field.value}
                  onValueChange={(value) => field.onChange(value ?? NO_LEVEL)}
                >
                  <SelectTrigger id="convert-child-level" onBlur={field.onBlur} className="w-full">
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
            <FieldError message={errors.child?.english_level?.message} />
          </div>
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="convert-child-meeting">Ссылка на занятия</Label>
          <Input
            id="convert-child-meeting"
            type="url"
            placeholder="Необязательно: https://…"
            aria-invalid={errors.child?.default_meeting_url ? true : undefined}
            {...register("child.default_meeting_url")}
          />
          <FieldError message={errors.child?.default_meeting_url?.message} />
        </div>
      </fieldset>

      <fieldset className="flex flex-col gap-4">
        <legend className="mb-2 text-sm font-medium">Родитель</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-2">
            <Label htmlFor="convert-parent-name">ФИО родителя</Label>
            <Input
              id="convert-parent-name"
              aria-invalid={errors.parent?.full_name ? true : undefined}
              {...register("parent.full_name")}
            />
            <FieldError message={errors.parent?.full_name?.message} />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="convert-parent-phone">Телефон родителя</Label>
            <Input
              id="convert-parent-phone"
              type="tel"
              aria-invalid={errors.parent?.phone ? true : undefined}
              {...register("parent.phone")}
            />
            <FieldError message={errors.parent?.phone?.message} />
          </div>
        </div>
      </fieldset>

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>
          Отмена
        </Button>
        <Button type="submit" disabled={convert.isPending}>
          {convert.isPending ? "Конвертируем…" : "Конвертировать"}
        </Button>
      </DialogFooter>
    </form>
  );
}

function ConvertedResult({ result, onClose }: { result: LeadConverted; onClose: () => void }) {
  return (
    <div className="flex flex-col gap-4">
      <CopyLinkCard
        url={result.invitation.url}
        expiresAt={result.invitation.expires_at}
        title="Ссылка-приглашение"
      />
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>
          Закрыть
        </Button>
        {/* Прежний маршрут остаётся смонтированным (Activity): закрываем диалог до перехода. */}
        <Link
          href={`/admin/families/${result.family_id}`}
          className={buttonVariants()}
          onClick={onClose}
        >
          Открыть семью
        </Link>
      </DialogFooter>
    </div>
  );
}

export function LeadConvertDialog({ lead }: { lead: LeadDetail }) {
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState<LeadConverted | null>(null);
  const convertible = lead.status === "trial_scheduled";

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (!next) setResult(null);
  }

  return (
    <>
      {/* После конвертации заявка уже `converted`: кнопка не нужна, а диалог с ссылкой остаётся открытым. */}
      {lead.status !== "converted" && (
        <div className="flex flex-col items-start gap-1">
          <Button type="button" disabled={!convertible} onClick={() => setOpen(true)}>
            Конвертировать в ученика
          </Button>
          {!convertible && <p className="text-sm text-muted-foreground">{CONVERT_HINT}</p>}
        </div>
      )}
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{result ? "Семья создана" : "Конвертация в ученика"}</DialogTitle>
            <DialogDescription>
              {result
                ? "Отправьте родителю ссылку: по ней он создаст аккаунт."
                : "Создадим семью, ребёнка и ссылку-приглашение для родителя."}
            </DialogDescription>
          </DialogHeader>
          {result ? (
            <ConvertedResult result={result} onClose={() => onOpenChange(false)} />
          ) : (
            <ConvertForm lead={lead} onConverted={setResult} onCancel={() => onOpenChange(false)} />
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
