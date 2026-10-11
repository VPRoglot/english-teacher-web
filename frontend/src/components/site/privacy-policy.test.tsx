import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { siteFixture } from "@/test/site-fixture";

import { PrivacyPolicy } from "./privacy-policy";

test("policy names the operator, retention, Telegram and contacts", () => {
  render(<PrivacyPolicy operatorName="Анна Смирнова" contacts={siteFixture.contacts} />);
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
    "Политика обработки персональных данных",
  );
  expect(screen.getByText(/Анна Смирнова/)).toBeInTheDocument();
  expect(screen.getByText(/12 месяцев/)).toBeInTheDocument();
  expect(screen.getAllByText(/Telegram/).length).toBeGreaterThan(0);
  expect(screen.getByRole("link", { name: "anna@example.com" })).toHaveAttribute(
    "href",
    "mailto:anna@example.com",
  );
});

test("policy falls back to the site form when there are no contacts", () => {
  render(
    <PrivacyPolicy
      operatorName="Анна Смирнова"
      contacts={{ telegram: null, whatsapp: null, phone: null, email: null, working_hours_text: null }}
    />,
  );
  expect(screen.getByText(/через форму на сайте/)).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /@|anna/ })).not.toBeInTheDocument();
});
