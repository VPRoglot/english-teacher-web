import type { Metadata } from "next";

import type { PublicSite } from "@/api/generated/model";

import { contactLinks } from "./site-format";

/** Метаданные страницы лендинга: заголовок, описание, canonical и Open Graph из блока `hero`. */
export function buildMetadata(site: PublicSite, siteUrl: string): Metadata {
  const { hero } = site;
  const title = `${hero.name} — ${hero.title}`;
  const description = hero.subtitle;
  return {
    metadataBase: new URL(siteUrl),
    title,
    description,
    alternates: { canonical: "/" },
    openGraph: {
      type: "website",
      locale: "ru_RU",
      url: "/",
      title,
      description,
      images: hero.photo
        ? [{ url: hero.photo.url, width: hero.photo.width, height: hero.photo.height }]
        : undefined,
    },
  };
}

/** Разметка schema.org: репетитор (`Person`) и по одной `Service` на каждую услугу. */
export function buildJsonLd(site: PublicSite, siteUrl: string): Record<string, unknown>[] {
  const { hero, contacts, services } = site;
  const telegram = contactLinks(contacts).find((link) => link.kind === "telegram");

  const person: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "Person",
    name: hero.name,
    jobTitle: "Репетитор по английскому языку",
    description: hero.subtitle,
    url: siteUrl,
    ...(hero.photo && { image: new URL(hero.photo.url, `${siteUrl}/`).toString() }),
    ...(contacts.email && { email: contacts.email }),
    ...(contacts.phone && { telephone: contacts.phone }),
    ...(telegram && { sameAs: [telegram.href] }),
  };

  const serviceItems = services.items.map((item) => ({
    "@context": "https://schema.org",
    "@type": "Service",
    name: item.title,
    description: item.description,
    serviceType: "Репетиторство по английскому языку",
    provider: { "@type": "Person", name: hero.name },
    offers: { "@type": "Offer", price: String(item.price_rub), priceCurrency: "RUB" },
  }));

  return [person, ...serviceItems];
}

/** JSON для `<script type="application/ld+json">`: `<` экранируется, чтобы текст не закрыл тег. */
export function jsonLdScript(data: unknown): string {
  return JSON.stringify(data).replace(/</g, "\\u003c");
}
