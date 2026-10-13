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

test("policy does not claim there are no third parties while Telegram gets notifications", () => {
  render(<PrivacyPolicy operatorName="Анна Смирнова" contacts={siteFixture.contacts} />);
  expect(screen.queryByText(/третьим лицам не передаются/)).not.toBeInTheDocument();
  expect(screen.getByText(/не продаются и не передаются третьим лицам/)).toBeInTheDocument();
  expect(
    screen.getByText(
      /имя родителя, возраст ребёнка, способ связи и контакт\s+для связи\) доставляется\s+репетитору через Telegram/,
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      /а также уведомления о запросах на\s+перенос и отмену занятий \(имя ученика и время занятия\)/,
    ),
  ).toBeInTheDocument();
  // Имя ребёнка, цель и удобное время в Telegram не уходят.
  expect(screen.queryByText(/имя ребёнка.*Telegram/)).not.toBeInTheDocument();
});

test("policy discloses Yandex SmartCaptcha and IP processing", () => {
  render(<PrivacyPolicy operatorName="Анна Смирнова" contacts={siteFixture.contacts} />);
  expect(
    screen.getByText(
      /Yandex SmartCaptcha: данные о взаимодействии с формой и IP-адрес\s+передаются ООО «Яндекс» для защиты от спама/,
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/IP-адрес: сайт обрабатывает его, чтобы ограничивать частоту отправки заявок/),
  ).toBeInTheDocument();
});

test("policy points to the site contacts when none are published", () => {
  render(
    <PrivacyPolicy
      operatorName="Анна Смирнова"
      contacts={{ telegram: null, whatsapp: null, phone: null, email: null, working_hours_text: null }}
    />,
  );
  expect(screen.getByText(/по контактам, указанным на сайте/)).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /@|anna/ })).not.toBeInTheDocument();
});

test("policy states how long deleted data stays in backups", () => {
  render(<PrivacyPolicy operatorName="Анна Смирнова" contacts={siteFixture.contacts} />);
  expect(
    screen.getByText("Если ведутся резервные копии, удалённые данные исчезают из них не позднее чем через 6 месяцев."),
  ).toBeInTheDocument();
});
