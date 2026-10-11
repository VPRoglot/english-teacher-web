import { render } from "@testing-library/react";
import { expect, test } from "vitest";

import { Markdown } from "./markdown";

test("renders markdown but never raw HTML or javascript: links", () => {
  const { container } = render(
    <Markdown>
      {"**Привет**<script>alert(1)</script><img src=x onerror=alert(1)> [x](javascript:alert(1))"}
    </Markdown>,
  );
  expect(container.querySelector("strong")).toHaveTextContent("Привет");
  expect(container.querySelector("script, img")).toBeNull();
  expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
});

test("external images are not rendered", () => {
  const { container } = render(<Markdown>{"до ![подпись](http://e.com/a.png) после"}</Markdown>);
  expect(container.querySelector("img")).toBeNull();
  expect(container).toHaveTextContent("до после");
});

test("markdown h1 and h2 render as h3 so the page keeps a single h1", () => {
  const { container } = render(<Markdown>{"# Заголовок\n\n## Подзаголовок\n\n### Малый"}</Markdown>);
  expect(container.querySelector("h1, h2")).toBeNull();
  expect([...container.querySelectorAll("h3")].map((h) => h.textContent)).toEqual([
    "Заголовок",
    "Подзаголовок",
    "Малый",
  ]);
});

test("external links open safely", () => {
  const { container } = render(<Markdown>{"[сайт](https://example.com)"}</Markdown>);
  const link = container.querySelector("a");
  expect(link).toHaveAttribute("href", "https://example.com");
  expect(link).toHaveAttribute("rel", "noopener noreferrer");
});
