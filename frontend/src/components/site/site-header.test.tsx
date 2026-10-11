import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { SiteHeader } from "./site-header";

test("anchors stay local by default", () => {
  render(<SiteHeader name="Анна" ctaText="Записаться" nav={[]} />);
  expect(screen.getByRole("link", { name: "Анна" })).toHaveAttribute("href", "#top");
  expect(screen.getByRole("link", { name: "Записаться" })).toHaveAttribute("href", "#trial");
});

test("homeHref points the name and CTA to the landing", () => {
  render(<SiteHeader name="Анна" ctaText="Записаться" nav={[]} homeHref="/" />);
  expect(screen.getByRole("link", { name: "Анна" })).toHaveAttribute("href", "/#top");
  expect(screen.getByRole("link", { name: "Записаться" })).toHaveAttribute("href", "/#trial");
});
