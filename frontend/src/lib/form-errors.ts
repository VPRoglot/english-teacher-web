import type { FieldValues, Path, UseFormSetError } from "react-hook-form";

import { ApiError } from "./api-fetch";

const FALLBACK_MESSAGE = "Что-то пошло не так. Попробуйте ещё раз.";

/** Текст ошибки для пользователя: сообщение `ApiError` либо общий текст. */
export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : FALLBACK_MESSAGE;
}

type FieldIssue = { loc: unknown[]; message: string };

function isFieldIssue(value: unknown): value is FieldIssue {
  if (typeof value !== "object" || value === null) return false;
  const issue = value as { loc?: unknown; message?: unknown };
  return Array.isArray(issue.loc) && typeof issue.message === "string";
}

/**
 * Раскладывает ошибки API по полям формы.
 *
 * Понимает 422 Pydantic (`details.fields[].loc`) и доменные ошибки с `details.field`.
 * Возвращает текст общей ошибки формы, если что-то не легло на поле, иначе `null`.
 */
export function applyApiErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  fields: readonly Path<T>[],
): string | null {
  if (!(error instanceof ApiError)) return errorMessage(error);

  const known = new Set<string>(fields);
  const { field, fields: issues } = error.details;

  if (typeof field === "string" && known.has(field)) {
    setError(field as Path<T>, { message: error.message });
    return null;
  }

  if (Array.isArray(issues) && issues.length > 0) {
    let unmapped = false;
    for (const issue of issues) {
      const name = isFieldIssue(issue) ? String(issue.loc[issue.loc.length - 1]) : null;
      if (isFieldIssue(issue) && name !== null && known.has(name)) {
        setError(name as Path<T>, { message: issue.message });
      } else {
        unmapped = true;
      }
    }
    return unmapped ? error.message : null;
  }

  return error.message;
}
