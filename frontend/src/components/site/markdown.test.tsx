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

test("external links open safely", () => {
  const { container } = render(<Markdown>{"[сайт](https://example.com)"}</Markdown>);
  const link = container.querySelector("a");
  expect(link).toHaveAttribute("href", "https://example.com");
  expect(link).toHaveAttribute("rel", "noopener noreferrer");
});
