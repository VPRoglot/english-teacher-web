import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { expect, test, vi } from "vitest";

import { MarkdownEditor } from "./markdown-editor";

function Harness({ initial = "", onChange }: { initial?: string; onChange?: (v: string) => void }) {
  const [value, setValue] = useState(initial);
  return (
    <MarkdownEditor
      label="Общая — видна семье"
      description="Родители увидят текст в кабинете"
      value={value}
      onChange={(next) => {
        setValue(next);
        onChange?.(next);
      }}
    />
  );
}

test("typing calls onChange and the label names the textarea", async () => {
  const onChange = vi.fn();
  const user = userEvent.setup();
  render(<Harness onChange={onChange} />);

  const textarea = screen.getByLabelText("Общая — видна семье");
  await user.type(textarea, "ab");

  expect(onChange).toHaveBeenLastCalledWith("ab");
  expect(textarea).toHaveValue("ab");
  expect(screen.getByText("Родители увидят текст в кабинете")).toBeInTheDocument();
});

test("preview renders markdown without raw html", async () => {
  const user = userEvent.setup();
  const { container } = render(<Harness initial="**жирный** <b>x</b>" />);

  await user.click(screen.getByRole("tab", { name: "Предпросмотр" }));

  expect(container.querySelector("strong")).toHaveTextContent("жирный");
  expect(container.querySelector("b")).toBeNull();
  expect(screen.queryByRole("textbox")).toBeNull();
  expect(screen.getByRole("tab", { name: "Предпросмотр" })).toHaveAttribute("aria-selected", "true");
});

test("preview of an empty text says «Пусто»", async () => {
  const user = userEvent.setup();
  render(<Harness initial="   " />);

  await user.click(screen.getByRole("tab", { name: "Предпросмотр" }));

  expect(screen.getByText("Пусто")).toBeInTheDocument();
});

test("switching back to the text tab keeps the value", async () => {
  const user = userEvent.setup();
  render(<Harness initial="привет" />);

  await user.click(screen.getByRole("tab", { name: "Предпросмотр" }));
  await user.click(screen.getByRole("tab", { name: "Текст" }));

  expect(screen.getByLabelText("Общая — видна семье")).toHaveValue("привет");
});
