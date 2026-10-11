"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { InvisibleSmartCaptcha } from "@yandex/smart-captcha";
import { useEffect, useState, type ReactNode } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { useSubmitLead } from "@/api/generated/endpoints/public/public";
import type { LeadCreate } from "@/api/generated/model";
import { SubmitLeadBody } from "@/api/generated/zod/public/public";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api-fetch";
import { applyApiErrors } from "@/lib/form-errors";
import { formatPhoneInput } from "@/lib/phone-mask";
import { captureUtm, readUtm } from "@/lib/utm";
import { cn } from "@/lib/utils";

const THANKS = "Спасибо! Заявка отправлена — я свяжусь с вами в ближайшее время.";
const RATE_LIMITED =
  "Слишком много заявок с этого устройства. Попробуйте позже или напишите напрямую.";
const CAPTCHA_UNAVAILABLE =
  "Не удалось загрузить проверку «я не робот». Проверьте соединение и попробуйте ещё раз.";
const AGE_RANGE_ERROR = "Возраст — от 3 до 18 лет";
/** Невидимая капча, которая не ответила за это время, считается недоступной. */
const CAPTCHA_TIMEOUT_MS = 20_000;

const russian = z.locales.ru().localeError;

/** Тексты клиентских ошибок по-русски: сгенерированная схема приходит без своих сообщений. */
const zodOptions = {
  error: (issue: z.core.$ZodRawIssue) => {
    if (issue.code === "too_small" && issue.origin === "string" && issue.minimum === 1) {
      return "Заполните поле";
    }
    if (issue.code === "too_big" && issue.origin === "string") {
      return `Не более ${String(issue.maximum)} символов`;
    }
    // Пустое числовое поле (valueAsNumber даёт NaN).
    if (issue.code === "invalid_type" && (issue.expected === "number" || issue.expected === "int")) {
      return "Введите число";
    }
    if ((issue.code === "too_small" || issue.code === "too_big") && issue.origin === "number") {
      return AGE_RANGE_ERROR;
    }
    return russian(issue);
  },
};

/** Номер введён целиком: российский — 11 цифр с кодом страны, иной — от 10 до 15 цифр. */
function isCompletePhone(value: string): boolean {
  const digits = value.replace(/\D/g, "").length;
  return value.startsWith("+7") ? digits === 11 : digits >= 10 && digits <= 15;
}

const schema = SubmitLeadBody.pick({
  parent_name: true,
  child_name: true,
  child_age: true,
  contact_method: true,
  messenger_handle: true,
  goal: true,
  preferred_time: true,
  website: true,
}).extend({
  phone: z.string().min(1).refine(isCompletePhone, "Введите номер полностью"),
  consent: z.boolean().refine((value) => value, {
    message: "Необходимо согласие на обработку персональных данных",
  }),
});

type Values = z.infer<typeof schema>;

const API_FIELDS = [
  "parent_name",
  "child_name",
  "child_age",
  "phone",
  "contact_method",
  "messenger_handle",
  "goal",
  "preferred_time",
  "consent",
] as const;

const CONTACT_METHODS = [
  { value: "telegram", label: "Telegram" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "phone", label: "Телефон" },
] as const;

function blankToNull(value: string | null | undefined): string | null {
  const trimmed = value?.trim();
  return trimmed ? trimmed : null;
}

function toLead(values: Values, captchaToken: string | undefined): LeadCreate {
  return {
    parent_name: values.parent_name,
    child_name: values.child_name,
    child_age: values.child_age,
    phone: values.phone,
    contact_method: values.contact_method,
    // Ник нужен только для Telegram; для остальных способов введённое ранее не отправляем.
    messenger_handle: values.contact_method === "telegram" ? blankToNull(values.messenger_handle) : null,
    goal: blankToNull(values.goal),
    preferred_time: blankToNull(values.preferred_time),
    consent: true,
    // Заполненный honeypot отправляем как есть: сервер молча отбросит такую заявку.
    ...(values.website ? { website: values.website } : {}),
    ...(captchaToken ? { captcha_token: captchaToken } : {}),
    ...readUtm(),
  };
}

function Field({
  id,
  label,
  error,
  className,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error && (
        <p id={`${id}-error`} className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

function invalidProps(id: string, error: string | undefined) {
  return error
    ? ({ "aria-invalid": true, "aria-describedby": `${id}-error` } as const)
    : ({} as const);
}

/** Форма заявки на пробное занятие. Без `captchaKey` капча не используется (dev). */
export function TrialForm({ captchaKey }: { captchaKey: string | null }) {
  const [done, setDone] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [challenge, setChallenge] = useState(false);
  // Виджет пересоздаётся после каждого токена: токен одноразовый.
  const [widgetKey, setWidgetKey] = useState(0);
  const [pending, setPending] = useState<Values | null>(null);
  const submit = useSubmitLead();

  const {
    register,
    control,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<Values>({
    resolver: zodResolver(schema, zodOptions),
    defaultValues: {
      parent_name: "",
      child_name: "",
      phone: "",
      contact_method: "telegram",
      messenger_handle: "",
      goal: "",
      preferred_time: "",
      website: "",
      consent: false,
    },
  });
  const contactMethod = useWatch({ control, name: "contact_method" });

  useEffect(() => {
    captureUtm(window.location.search);
  }, []);

  // Сторож: если виджет завис и не сообщил ни об успехе, ни об ошибке, форма не должна
  // оставаться заблокированной. Таймер снимается при любом выходе из проверки и при размонтировании.
  useEffect(() => {
    if (!challenge) return;
    const timer = setTimeout(abortCaptcha, CAPTCHA_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [challenge]);

  function send(values: Values, captchaToken: string | undefined) {
    setFormError(null);
    submit.mutate(
      { data: toLead(values, captchaToken) },
      {
        onSuccess: () => setDone(true),
        onError: (error) =>
          setFormError(
            error instanceof ApiError && error.status === 429
              ? RATE_LIMITED
              : applyApiErrors(error, setError, API_FIELDS),
          ),
      },
    );
  }

  function onValid(values: Values) {
    if (!captchaKey) {
      send(values, undefined);
      return;
    }
    setFormError(null);
    setPending(values);
    setChallenge(true);
  }

  function onCaptchaSuccess(token: string) {
    const values = pending;
    setPending(null);
    setChallenge(false);
    setWidgetKey((key) => key + 1);
    if (values) send(values, token);
  }

  /** Проверка не состоялась (сбой сети или скрипта, истёк токен, виджет завис). */
  function abortCaptcha() {
    setPending(null);
    setChallenge(false);
    setWidgetKey((key) => key + 1); // свежий виджет вместо зависшего
    setFormError(CAPTCHA_UNAVAILABLE);
  }

  function onCaptchaHidden() {
    // Виджет может сообщить о закрытии раньше, чем пришёл токен: `pending` не трогаем,
    // чтобы опоздавший `success` всё равно отправил заявку. Новая отправка перезапишет `pending`.
    setChallenge(false);
  }

  function onCaptchaTokenExpired() {
    if (challenge) abortCaptcha();
  }

  if (done) {
    return (
      <p role="status" className="text-lg font-medium">
        {THANKS}
      </p>
    );
  }

  const busy = submit.isPending || challenge;

  return (
    <form onSubmit={handleSubmit(onValid)} noValidate className="relative grid gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="trial-parent-name" label="Ваше имя" error={errors.parent_name?.message}>
          <Input
            id="trial-parent-name"
            autoComplete="name"
            className="h-11"
            {...invalidProps("trial-parent-name", errors.parent_name?.message)}
            {...register("parent_name")}
          />
        </Field>
        <Field id="trial-child-name" label="Имя ребёнка" error={errors.child_name?.message}>
          <Input
            id="trial-child-name"
            className="h-11"
            {...invalidProps("trial-child-name", errors.child_name?.message)}
            {...register("child_name")}
          />
        </Field>
        <Field id="trial-child-age" label="Возраст ребёнка" error={errors.child_age?.message}>
          <Input
            id="trial-child-age"
            type="number"
            inputMode="numeric"
            min={3}
            max={18}
            className="h-11"
            {...invalidProps("trial-child-age", errors.child_age?.message)}
            {...register("child_age", { valueAsNumber: true })}
          />
        </Field>
        <Field id="trial-phone" label="Телефон" error={errors.phone?.message}>
          <Controller
            control={control}
            name="phone"
            render={({ field }) => (
              <Input
                id="trial-phone"
                type="tel"
                inputMode="tel"
                autoComplete="tel"
                placeholder="+7 (999) 123-45-67"
                maxLength={24}
                className="h-11"
                name={field.name}
                ref={field.ref}
                value={field.value}
                onBlur={field.onBlur}
                onChange={(event) => field.onChange(formatPhoneInput(event.target.value))}
                {...invalidProps("trial-phone", errors.phone?.message)}
              />
            )}
          />
        </Field>
      </div>

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-2 text-sm font-medium">Как удобнее связаться</legend>
        <div className="flex flex-wrap gap-2">
          {CONTACT_METHODS.map(({ value, label }) => (
            <label
              key={value}
              className="flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border border-input bg-background px-4 text-base has-checked:border-primary has-checked:bg-primary/10 has-focus-visible:ring-3 has-focus-visible:ring-ring/50"
            >
              <input
                type="radio"
                value={value}
                className="size-4 accent-primary"
                {...register("contact_method")}
              />
              {label}
            </label>
          ))}
        </div>
      </fieldset>

      {contactMethod === "telegram" && (
        <Field id="trial-handle" label="Ник в Telegram" error={errors.messenger_handle?.message}>
          <Input
            id="trial-handle"
            placeholder="@username"
            autoCapitalize="none"
            autoComplete="off"
            className="h-11"
            {...invalidProps("trial-handle", errors.messenger_handle?.message)}
            {...register("messenger_handle")}
          />
        </Field>
      )}

      <Field id="trial-goal" label="Цель занятий" error={errors.goal?.message}>
        <Textarea
          id="trial-goal"
          rows={3}
          placeholder="Например: подтянуть школьную программу или заговорить свободнее"
          {...invalidProps("trial-goal", errors.goal?.message)}
          {...register("goal")}
        />
      </Field>
      <Field id="trial-time" label="Удобное время" error={errors.preferred_time?.message}>
        <Input
          id="trial-time"
          placeholder="Например: будни после 17:00"
          className="h-11"
          {...invalidProps("trial-time", errors.preferred_time?.message)}
          {...register("preferred_time")}
        />
      </Field>

      <div className="flex flex-col gap-2">
        <div className="flex items-start gap-2">
          <Controller
            control={control}
            name="consent"
            render={({ field }) => (
              <Checkbox
                id="trial-consent"
                checked={field.value}
                onCheckedChange={field.onChange}
                onBlur={field.onBlur}
                aria-invalid={errors.consent ? true : undefined}
                className="mt-0.5"
              />
            )}
          />
          <Label htmlFor="trial-consent" className="block leading-snug font-normal">
            Согласен(на) на обработку персональных данных в соответствии с{" "}
            <a
              href="/privacy"
              target="_blank"
              rel="noopener noreferrer"
              className="underline underline-offset-2"
            >
              политикой
            </a>
          </Label>
        </div>
        {errors.consent && <p className="text-sm text-destructive">{errors.consent.message}</p>}
      </div>

      {/* Honeypot: человек его не видит и не фокусирует, простой бот заполнит. */}
      <div aria-hidden="true" className="sr-only">
        <label>
          Сайт
          <input type="text" tabIndex={-1} autoComplete="off" {...register("website")} />
        </label>
      </div>

      {captchaKey && (
        <InvisibleSmartCaptcha
          key={widgetKey}
          sitekey={captchaKey}
          language="ru"
          visible={challenge}
          onSuccess={onCaptchaSuccess}
          onChallengeHidden={onCaptchaHidden}
          onNetworkError={abortCaptcha}
          onJavascriptError={abortCaptcha}
          onTokenExpired={onCaptchaTokenExpired}
        />
      )}

      {formError && (
        <Alert variant="destructive">
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      )}
      <Button type="submit" size="lg" className="h-11 w-full sm:w-auto" disabled={busy}>
        {busy ? "Отправляем…" : "Записаться на пробное"}
      </Button>
    </form>
  );
}
