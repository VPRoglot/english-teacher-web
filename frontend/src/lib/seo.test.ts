import { expect, test } from "vitest";

import { siteFixture } from "@/test/site-fixture";

import { buildJsonLd, buildMetadata, jsonLdScript } from "./seo";

test("metadata uses hero and absolute og image", () => {
  const m = buildMetadata(siteFixture, "https://anna.example");
  expect(m.title).toBe(`${siteFixture.hero.name} — ${siteFixture.hero.title}`);
  expect(m.description).toBe(siteFixture.hero.subtitle);
  expect(m.metadataBase?.toString()).toBe("https://anna.example/");
  expect(m.alternates).toEqual({ canonical: "/" });
  expect(m.openGraph?.images).toEqual([{ url: "/media/site/hero.jpg", width: 800, height: 1000 }]);
});

test("metadata omits og images without a hero photo", () => {
  const site = { ...siteFixture, hero: { ...siteFixture.hero, photo: null } };
  expect(buildMetadata(site, "https://anna.example").openGraph?.images).toBeUndefined();
});

test("json-ld has a Person and one Service per item", () => {
  const [person, ...services] = buildJsonLd(siteFixture, "https://anna.example");
  expect(person).toMatchObject({
    "@type": "Person",
    name: siteFixture.hero.name,
    image: "https://anna.example/media/site/hero.jpg",
    email: "anna@example.com",
    telephone: "+79991234567",
    sameAs: ["https://t.me/anna_english"],
  });
  expect(services).toHaveLength(2);
  expect(services[0]).toMatchObject({
    "@type": "Service",
    provider: { "@type": "Person", name: siteFixture.hero.name },
    offers: { "@type": "Offer", price: "0", priceCurrency: "RUB" },
  });
});

test("json-ld omits empty person fields", () => {
  const site = {
    ...siteFixture,
    hero: { ...siteFixture.hero, photo: null },
    contacts: { ...siteFixture.contacts, telegram: null, phone: null, email: null },
  };
  const [person] = buildJsonLd(site, "https://anna.example");
  expect(person).not.toHaveProperty("image");
  expect(person).not.toHaveProperty("email");
  expect(person).not.toHaveProperty("telephone");
  expect(person).not.toHaveProperty("sameAs");
});

test("json-ld script cannot close the script tag", () => {
  const out = jsonLdScript(
    buildJsonLd(
      { ...siteFixture, hero: { ...siteFixture.hero, name: "</script><script>alert(1)</script>" } },
      "https://a.example",
    ),
  );
  expect(out).not.toContain("</script>");
  expect(JSON.parse(out)[0].name).toBe("</script><script>alert(1)</script>");
});
