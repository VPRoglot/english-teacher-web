import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import type { PublicSite } from "@/api/generated/model";
import { siteFixture } from "@/test/site-fixture";

import { Landing } from "./landing";

function renderLanding(site: PublicSite, captchaKey?: string | null) {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <Landing site={site} captchaKey={captchaKey} />
    </QueryClientProvider>,
  );
}

test("renders sections in order with anchors", () => {
  renderLanding(siteFixture);
  const ids = [...document.querySelectorAll("main section[id]")].map((s) => s.id);
  expect(ids).toEqual(["about", "services", "reviews", "faq", "trial", "contacts"]);
  expect(screen.getByRole("link", { name: siteFixture.hero.cta_text })).toHaveAttribute(
    "href",
    "#trial",
  );
  expect(screen.getByRole("img", { name: siteFixture.hero.name })).toHaveAttribute("width", "800");
});

test("hides empty sections and their nav links", () => {
  const site: PublicSite = {
    ...siteFixture,
    reviews: { items: [] },
    faq: { items: [] },
    contacts: { telegram: null, whatsapp: null, phone: null, email: null, working_hours_text: null },
  };
  renderLanding(site);
  expect(screen.queryByRole("heading", { name: "Отзывы" })).toBeNull();
  expect(screen.queryByRole("link", { name: "Отзывы" })).toBeNull();
  expect(screen.queryByRole("link", { name: "Контакты" })).toBeNull();
  expect(document.getElementById("contacts")).toBeNull();
  // Без контактов заявка остаётся единственным способом связи, строки «напишите напрямую» нет.
  expect(screen.getByRole("button", { name: "Записаться на пробное" })).toBeInTheDocument();
  expect(screen.queryByText("или напишите напрямую")).toBeNull();
});

test("navigation links to present sections", () => {
  renderLanding(siteFixture);
  const nav = screen.getByRole("navigation", { name: "Разделы сайта" });
  expect(within(nav).getByRole("link", { name: "Услуги" })).toHaveAttribute("href", "#services");
  expect(within(nav).getByRole("link", { name: "Контакты" })).toHaveAttribute("href", "#contacts");
});

test("hero without photo renders no image", () => {
  const site: PublicSite = { ...siteFixture, hero: { ...siteFixture.hero, photo: null } };
  renderLanding(site);
  expect(screen.queryByRole("img")).toBeNull();
});

test("duplicate credentials are all rendered without key warnings", () => {
  const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
  const site: PublicSite = {
    ...siteFixture,
    about: { ...siteFixture.about, credentials: ["Диплом", "Диплом"] },
  };
  renderLanding(site);
  expect(screen.getAllByText("Диплом")).toHaveLength(2);
  expect(consoleError).not.toHaveBeenCalled();
  consoleError.mockRestore();
});

test("service shows duration, format and free price", () => {
  renderLanding(siteFixture);
  expect(screen.getByText("30 мин · Онлайн")).toBeInTheDocument();
  expect(screen.getByText("Бесплатно")).toBeInTheDocument();
  expect(screen.getByText(/^1\s500\s₽$/)).toBeInTheDocument();
});

test("review shows child age with correct plural", () => {
  renderLanding(siteFixture);
  expect(screen.getByText("ребёнку 9 лет")).toBeInTheDocument();
});

test("faq uses details and summary", () => {
  renderLanding(siteFixture);
  const summary = screen.getByText("Как проходят занятия?");
  expect(summary.tagName).toBe("SUMMARY");
  expect(summary.closest("details")).toHaveTextContent("Онлайн в Zoom или Telegram.");
});

test("about text is rendered as markdown without raw html", () => {
  const site: PublicSite = {
    ...siteFixture,
    about: { ...siteFixture.about, text: "Текст **жирный** <script>alert(1)</script>" },
  };
  renderLanding(site);
  expect(document.querySelector("#about strong")).toHaveTextContent("жирный");
  expect(document.querySelector("script")).toBeNull();
});

test("trial section has the request form and keeps direct contacts", () => {
  renderLanding(siteFixture);
  const trial = document.getElementById("trial") as HTMLElement;
  expect(within(trial).getByRole("button", { name: "Записаться на пробное" })).toBeInTheDocument();
  expect(within(trial).getByLabelText("Ваше имя")).toBeInTheDocument();
  expect(within(trial).getByText("или напишите напрямую")).toBeInTheDocument();
  expect(within(trial).getByRole("link", { name: "anna@example.com" })).toBeInTheDocument();
});

test("trial and contacts expose contact links", () => {
  renderLanding(siteFixture);
  expect(screen.getAllByRole("link", { name: "anna@example.com" })).toHaveLength(2);
  expect(screen.getByText("Пн–Пт 10:00–20:00")).toBeInTheDocument();
});

test("footer links to privacy policy and login", () => {
  renderLanding(siteFixture);
  const footer = screen.getByRole("contentinfo");
  expect(
    within(footer).getByRole("link", { name: "Политика обработки персональных данных" }),
  ).toHaveAttribute("href", "/privacy");
  expect(within(footer).getByRole("link", { name: "Вход для учеников" })).toHaveAttribute(
    "href",
    "/login",
  );
});
