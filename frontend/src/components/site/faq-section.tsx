import { ChevronDown } from "lucide-react";

import type { FaqItem } from "@/api/generated/model";

import { Markdown } from "./markdown";

export function FaqSection({ items }: { items: FaqItem[] }) {
  return (
    <section id="faq" aria-labelledby="faq-title" className="scroll-mt-16 bg-muted/40 py-12 sm:py-16">
      <div className="mx-auto w-full max-w-3xl px-4 sm:px-6">
        <h2 id="faq-title" className="mb-6 text-2xl font-semibold tracking-tight">
          Частые вопросы
        </h2>
        <div className="space-y-3">
          {items.map((item, index) => (
            <details
              key={`${index}-${item.question}`}
              className="group rounded-xl bg-card px-4 ring-1 ring-foreground/10"
            >
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-4 font-medium [&::-webkit-details-marker]:hidden">
                {item.question}
                <ChevronDown
                  aria-hidden="true"
                  className="size-5 shrink-0 text-muted-foreground transition-transform group-open:rotate-180"
                />
              </summary>
              <div className="pb-4 text-muted-foreground">
                <Markdown>{item.answer}</Markdown>
              </div>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}
