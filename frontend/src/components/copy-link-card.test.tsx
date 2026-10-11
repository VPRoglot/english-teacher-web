import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { CopyLinkCard } from "./copy-link-card";

test("CopyLinkCard копирует ссылку", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
  render(
    <CopyLinkCard title="Приглашение" url="http://x/invite/t" expiresAt="2026-10-18T09:00:00Z" />,
  );
  expect(screen.getByDisplayValue("http://x/invite/t")).toHaveAttribute("readonly");
  await userEvent.click(screen.getByRole("button", { name: "Скопировать" }));
  expect(writeText).toHaveBeenCalledWith("http://x/invite/t");
  expect(await screen.findByText("Скопировано")).toBeInTheDocument();
  expect(screen.getByText(/18\.10\.2026 12:00/)).toBeInTheDocument();
});
