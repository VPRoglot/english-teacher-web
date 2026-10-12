"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import type { z } from "zod";

import {
  getGetTutorSettingsAdminQueryKey,
  useGetTutorSettingsAdmin,
  useUpdateTutorSettingsAdmin,
} from "@/api/generated/endpoints/admin/admin";
import type { ScheduleSettings } from "@/api/generated/model";
import { UpdateTutorSettingsAdminBody } from "@/api/generated/zod/admin/admin";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Label } from "@/components/ui/label";
import { DEFAULT_TIME_ZONE } from "@/lib/datetime";
import { applyApiErrors, errorMessage } from "@/lib/form-errors";

import { BlockForm, TextField, zodOptions } from "../site/site-form";

type FormValues = z.input<typeof UpdateTutorSettingsAdminBody>;

const FIELDS = ["timezone", "cancel_policy_hours"] as const;

const SELECT_CLASS =
  "h-8 w-full min-w-0 rounded-lg border border-input bg-transparent px-2 py-1 text-base transition-colors outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 md:text-sm dark:bg-input/30";

/** Пояса браузера с `Europe/Moscow` первым; сохранённый пояс, которого нет в списке, добавляется. */
function timeZoneOptions(current: string): string[] {
  let supported: string[] = [];
  try {
    supported = Intl.supportedValuesOf("timeZone");
  } catch {
    // Старый браузер без Intl.supportedValuesOf: остаются Москва и сохранённое значение.
  }
  const rest = supported.filter((zone) => zone !== DEFAULT_TIME_ZONE);
  const options = [DEFAULT_TIME_ZONE, ...rest];
  return options.includes(current) ? options : [...options, current];
}

function invalidateSchedule(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: getGetTutorSettingsAdminQueryKey() });
  // Смена пояса пересоздаёт будущие занятия серий: списки и карточки занятий и серий устарели.
  void queryClient.invalidateQueries({
    predicate: ({ queryKey }) =>
      typeof queryKey[0] === "string" &&
      (queryKey[0].startsWith("/api/admin/lessons") || queryKey[0].startsWith("/api/admin/series")),
  });
}

function SettingsFields({ settings }: { settings: ScheduleSettings }) {
  const queryClient = useQueryClient();
  const update = useUpdateTutorSettingsAdmin();
  const [formError, setFormError] = useState<string | null>(null);
  const zones = useMemo(() => timeZoneOptions(settings.timezone), [settings.timezone]);
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors },
  } = useForm<FormValues, unknown, z.output<typeof UpdateTutorSettingsAdminBody>>({
    resolver: zodResolver(UpdateTutorSettingsAdminBody, zodOptions),
    defaultValues: {
      timezone: settings.timezone,
      cancel_policy_hours: settings.cancel_policy_hours,
    },
  });

  function onSubmit(values: z.output<typeof UpdateTutorSettingsAdminBody>) {
    setFormError(null);
    update.mutate(
      { data: values },
      {
        onSuccess: (saved) => {
          reset({ timezone: saved.timezone, cancel_policy_hours: saved.cancel_policy_hours });
          toast.success("Настройки сохранены");
          invalidateSchedule(queryClient);
        },
        onError: (error) => setFormError(applyApiErrors(error, setError, FIELDS)),
      },
    );
  }

  return (
    <BlockForm
      title="Расписание"
      onSubmit={handleSubmit(onSubmit)}
      formError={formError}
      pending={update.isPending}
    >
      <div className="flex flex-col gap-2">
        <Label htmlFor="settings-timezone">Часовой пояс</Label>
        <select
          id="settings-timezone"
          aria-invalid={errors.timezone ? true : undefined}
          className={SELECT_CLASS}
          {...register("timezone")}
        >
          {zones.map((zone) => (
            <option key={zone} value={zone}>
              {zone}
            </option>
          ))}
        </select>
        {errors.timezone && <p className="text-sm text-destructive">{errors.timezone.message}</p>}
        <p className="text-sm text-muted-foreground">
          Смена пояса сохраняет местное время регулярных занятий
        </p>
      </div>
      <TextField
        id="settings-cancel-policy"
        label="Порог поздней отмены, часов"
        type="number"
        inputMode="numeric"
        min={0}
        max={168}
        error={errors.cancel_policy_hours?.message}
        {...register("cancel_policy_hours", { valueAsNumber: true })}
      />
    </BlockForm>
  );
}

function Skeleton() {
  return <div role="status" aria-label="Загрузка" className="h-48 animate-pulse rounded-xl bg-muted" />;
}

/** Загружает настройки репетитора и показывает форму; сохранённые значения возвращает сервер. */
export function SettingsForm() {
  const query = useGetTutorSettingsAdmin();
  if (query.data) return <SettingsFields settings={query.data} />;
  if (query.error) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{errorMessage(query.error)}</AlertDescription>
      </Alert>
    );
  }
  return <Skeleton />;
}
