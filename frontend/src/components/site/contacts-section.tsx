import type { ContactLink } from "@/lib/site-format";

import { ContactLinks } from "./contact-links";

export function ContactsSection({
  links,
  workingHours,
}: {
  links: ContactLink[];
  workingHours: string | null | undefined;
}) {
  return (
    <section id="contacts" aria-labelledby="contacts-title" className="scroll-mt-16 bg-muted/40 py-12 sm:py-16">
      <div className="mx-auto w-full max-w-5xl space-y-5 px-4 sm:px-6">
        <h2 id="contacts-title" className="text-2xl font-semibold tracking-tight">
          Контакты
        </h2>
        {links.length > 0 && <ContactLinks links={links} />}
        {workingHours && <p className="text-muted-foreground">{workingHours}</p>}
      </div>
    </section>
  );
}
