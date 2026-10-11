import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import Home from "./page";

test("главная показывает заголовок-заглушку", () => {
  render(<Home />);
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
    "Сайт репетитора по английскому",
  );
});
