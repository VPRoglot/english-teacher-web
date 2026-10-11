import type { ContactLink } from "@/lib/site-format";

import { ContactLinks } from "./contact-links";

/** Временная секция: форма заявки появится в плане 4. */
export function TrialSection({ links }: { links: ContactLink[] }) {
  return (
    <section id="trial" aria-labelledby="trial-title" className="scroll-mt-16 py-12 sm:py-16">
      <div className="mx-auto w-full max-w-5xl px-4 sm:px-6">
        <div className="space-y-5 rounded-2xl bg-secondary px-5 py-8 sm:px-8">
          <h2 id="trial-title" className="text-2xl font-semibold tracking-tight">
            Пробное занятие
          </h2>
          {links.length > 0 ? (
            <>
              <p className="text-lg">
                Напишите удобным способом — договоримся о времени пробного занятия
              </p>
              <ContactLinks links={links} />
            </>
          ) : (
            <p className="text-lg text-muted-foreground">Контакты скоро появятся</p>
          )}
        </div>
      </div>
    </section>
  );
}
