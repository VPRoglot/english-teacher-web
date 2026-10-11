import type { PublicSite } from "@/api/generated/model";
import { contactLinks } from "@/lib/site-format";

import { AboutSection } from "./about-section";
import { ContactsSection } from "./contacts-section";
import { FaqSection } from "./faq-section";
import { HeroSection } from "./hero-section";
import { ReviewsSection } from "./reviews-section";
import { ServicesSection } from "./services-section";
import { SiteFooter } from "./site-footer";
import { SiteHeader, type SiteNavItem } from "./site-header";
import { TrialSection } from "./trial-section";

/** Лендинг целиком из блоков контента. Секции без данных не выводятся. */
export function Landing({ site }: { site: PublicSite }) {
  const { hero, about, services, reviews, faq, contacts } = site;
  const links = contactLinks(contacts);
  const hasContacts = links.length > 0 || Boolean(contacts.working_hours_text);

  const nav: SiteNavItem[] = [
    { href: "#about", label: "Обо мне" },
    ...(services.items.length > 0 ? [{ href: "#services", label: "Услуги" }] : []),
    ...(reviews.items.length > 0 ? [{ href: "#reviews", label: "Отзывы" }] : []),
    ...(faq.items.length > 0 ? [{ href: "#faq", label: "Вопросы" }] : []),
    ...(hasContacts ? [{ href: "#contacts", label: "Контакты" }] : []),
  ];

  return (
    <>
      <SiteHeader name={hero.name} ctaText={hero.cta_text} nav={nav} />
      <main id="top" className="flex-1">
        <HeroSection hero={hero} />
        <AboutSection about={about} />
        {services.items.length > 0 && <ServicesSection items={services.items} />}
        {reviews.items.length > 0 && <ReviewsSection items={reviews.items} />}
        {faq.items.length > 0 && <FaqSection items={faq.items} />}
        <TrialSection links={links} />
        {hasContacts && <ContactsSection links={links} workingHours={contacts.working_hours_text} />}
      </main>
      <SiteFooter name={hero.name} />
    </>
  );
}
