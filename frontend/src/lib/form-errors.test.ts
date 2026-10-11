import { expect, test, vi } from "vitest";

import { ApiError } from "./api-fetch";
import { applyApiErrors, applyPasswordPolicyError, errorMessage } from "./form-errors";

type Form = { email: string; password: string; current_password: string };

test("ошибки Pydantic ложатся на поля", () => {
  const setError = vi.fn();
  const err = new ApiError(422, "validation_error", "Ошибка валидации", {
    fields: [{ loc: ["body", "email"], message: "bad", type: "value_error" }],
  });
  expect(applyApiErrors<Form>(err, setError, ["email", "password"])).toBeNull();
  expect(setError).toHaveBeenCalledWith("email", { message: "bad" });
});

test("поле вне списка даёт общую ошибку формы", () => {
  const setError = vi.fn();
  const err = new ApiError(422, "validation_error", "Ошибка валидации", {
    fields: [
      { loc: ["body", "email"], message: "bad", type: "value_error" },
      { loc: ["body", "other"], message: "x", type: "value_error" },
    ],
  });
  expect(applyApiErrors<Form>(err, setError, ["email"])).toBe("Ошибка валидации");
  expect(setError).toHaveBeenCalledTimes(1);
});

test("доменная ошибка с details.field ложится на поле", () => {
  const setError = vi.fn();
  const err = new ApiError(400, "invalid_current_password", "Неверный текущий пароль", {
    field: "current_password",
  });
  expect(applyApiErrors<Form>(err, setError, ["current_password", "password"])).toBeNull();
  expect(setError).toHaveBeenCalledWith("current_password", { message: "Неверный текущий пароль" });
});

test("неизвестная ошибка → общий текст", () => {
  const setError = vi.fn();
  const err = new ApiError(409, "email_taken", "Email уже используется");
  expect(applyApiErrors<Form>(err, setError, ["email"])).toBe("Email уже используется");
  expect(setError).not.toHaveBeenCalled();
});

test("не ApiError → общий текст по умолчанию", () => {
  const setError = vi.fn();
  expect(applyApiErrors<Form>(new Error("boom"), setError, ["email"])).toBe(
    "Что-то пошло не так. Попробуйте ещё раз.",
  );
});

test("ошибка политики пароля ложится на поле password", () => {
  const setError = vi.fn();
  const err = new ApiError(422, "password_too_common", "Слишком простой пароль");
  expect(applyPasswordPolicyError<Form>(err, setError)).toBe(true);
  expect(setError).toHaveBeenCalledWith("password", { message: "Слишком простой пароль" });
});

test("прочие ошибки политикой пароля не обрабатываются", () => {
  const setError = vi.fn();
  const taken = new ApiError(409, "email_taken", "Занят");
  expect(applyPasswordPolicyError<Form>(taken, setError)).toBe(false);
  expect(applyPasswordPolicyError<Form>(new Error("boom"), setError)).toBe(false);
  expect(setError).not.toHaveBeenCalled();
});

test("errorMessage", () => {
  expect(errorMessage(new ApiError(500, "x", "Сбой"))).toBe("Сбой");
  expect(errorMessage(new Error("boom"))).toBe("Что-то пошло не так. Попробуйте ещё раз.");
  expect(errorMessage(undefined)).toBe("Что-то пошло не так. Попробуйте ещё раз.");
});
