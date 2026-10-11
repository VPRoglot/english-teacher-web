import { render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import type { PublicSite } from "@/api/generated/model";
import { siteFixture } from "@/test/site-fixture";

import { Landing } from "./landing";

test("renders sections in order with anchors", () => {
  render(<Landing site={siteFixture} />);
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
  render(<Landing site={site} />);
  expect(screen.queryByRole("heading", { name: "Отзывы" })).toBeNull();
  expect(screen.queryByRole("link", { name: "Отзывы" })).toBeNull();
  expect(screen.queryByRole("link", { name: "Контакты" })).toBeNull();
  expect(document.getElementById("contacts")).toBeNull();
  expect(screen.getByText("Контакты скоро появятся")).toBeInTheDocument();
});

test("navigation links to present sections", () => {
  render(<Landing site={siteFixture} />);
  const nav = screen.getByRole("navigation", { name: "Разделы сайта" });
  expect(within(nav).getByRole("link", { name: "Услуги" })).toHaveAttribute("href", "#services");
  expect(within(nav).getByRole("link", { name: "Контакты" })).toHaveAttribute("href", "#contacts");
});

test("hero without photo renders no image", () => {
  const site: PublicSite = { ...siteFixture, hero: { ...siteFixture.hero, photo: null } };
  render(<Landing site={site} />);
  expect(screen.queryByRole("img")).toBeNull();
});

test("duplicate credentials are all rendered without key warnings", () => {
  const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
  const site: PublicSite = {
    ...siteFixture,
    about: { ...siteFixture.about, credentials: ["Диплом", "Диплом"] },
  };
  render(<Landing site={site} />);
  expect(screen.getAllByText("Диплом")).toHaveLength(2);
  expect(consoleError).not.toHaveBeenCalled();
  consoleError.mockRestore();
});

test("service shows duration, format and free price", () => {
  render(<Landing site={siteFixture} />);
  expect(screen.getByText("30 мин · Онлайн")).toBeInTheDocument();
  expect(screen.getByText("Бесплатно")).toBeInTheDocument();
  expect(screen.getByText(/^1\s500\s₽$/)).toBeInTheDocument();
});

test("review shows child age with correct plural", () => {
  render(<Landing site={siteFixture} />);
  expect(screen.getByText("ребёнку 9 лет")).toBeInTheDocument();
});

test("faq uses details and summary", () => {
  render(<Landing site={siteFixture} />);
  const summary = screen.getByText("Как проходят занятия?");
  expect(summary.tagName).toBe("SUMMARY");
  expect(summary.closest("details")).toHaveTextContent("Онлайн в Zoom или Telegram.");
});

test("about text is rendered as markdown without raw html", () => {
  const site: PublicSite = {
    ...siteFixture,
    about: { ...siteFixture.about, text: "Текст **жирный** <script>alert(1)</script>" },
  };
  render(<Landing site={site} />);
  expect(document.querySelector("#about strong")).toHaveTextContent("жирный");
  expect(document.querySelector("script")).toBeNull();
});

test("trial and contacts expose contact links", () => {
  render(<Landing site={siteFixture} />);
  expect(screen.getByText(/договоримся о времени пробного занятия/)).toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: "anna@example.com" })).toHaveLength(2);
  expect(screen.getByText("Пн–Пт 10:00–20:00")).toBeInTheDocument();
});

test("footer links to privacy policy and login", () => {
  render(<Landing site={siteFixture} />);
  const footer = screen.getByRole("contentinfo");
  expect(
    within(footer).getByRole("link", { name: "Политика обработки персональных данных" }),
  ).toHaveAttribute("href", "/privacy");
  expect(within(footer).getByRole("link", { name: "Вход для учеников" })).toHaveAttribute(
    "href",
    "/login",
  );
});
