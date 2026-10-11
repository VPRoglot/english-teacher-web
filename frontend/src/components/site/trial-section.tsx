import type { ContactLink } from "@/lib/site-format";

import { ContactLinks } from "./contact-links";
import { TrialForm } from "./trial-form";

/** Заявка на пробное занятие; контакты остаются запасным способом связи. */
export function TrialSection({
  links,
  captchaKey = null,
}: {
  links: ContactLink[];
  captchaKey?: string | null;
}) {
  return (
    <section id="trial" aria-labelledby="trial-title" className="scroll-mt-16 py-12 sm:py-16">
      <div className="mx-auto w-full max-w-5xl px-4 sm:px-6">
        <div className="space-y-6 rounded-2xl bg-secondary px-5 py-8 sm:px-8">
          <div className="space-y-2">
            <h2 id="trial-title" className="text-2xl font-semibold tracking-tight">
              Пробное занятие
            </h2>
            <p className="text-lg">
              Оставьте заявку — я свяжусь с вами и договорюсь о времени пробного занятия
            </p>
          </div>
          <TrialForm captchaKey={captchaKey} />
          {links.length > 0 && (
            <div className="space-y-3 border-t border-border pt-6">
              <p className="text-muted-foreground">или напишите напрямую</p>
              <ContactLinks links={links} />
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
