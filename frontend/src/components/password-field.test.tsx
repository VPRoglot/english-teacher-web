import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { expect, test } from "vitest";

import { PasswordField } from "./password-field";

test("PasswordField переключает видимость и пробрасывает ref", async () => {
  const ref = createRef<HTMLInputElement>();
  render(<PasswordField ref={ref} aria-label="Пароль" />);
  const input = screen.getByLabelText("Пароль");
  expect(input).toHaveAttribute("type", "password");
  expect(ref.current).toBe(input);
  await userEvent.click(screen.getByRole("button", { name: "Показать пароль" }));
  expect(input).toHaveAttribute("type", "text");
  await userEvent.click(screen.getByRole("button", { name: "Скрыть пароль" }));
  expect(input).toHaveAttribute("type", "password");
});
