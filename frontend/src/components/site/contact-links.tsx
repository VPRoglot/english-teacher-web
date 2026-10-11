import { Mail, MessageCircle, Phone, Send, type LucideIcon } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import type { ContactLink } from "@/lib/site-format";
import { cn } from "@/lib/utils";

const ICONS: Record<ContactLink["kind"], LucideIcon> = {
  telegram: Send,
  whatsapp: MessageCircle,
  phone: Phone,
  email: Mail,
};

export function ContactLinks({ links, className }: { links: ContactLink[]; className?: string }) {
  return (
    <ul className={cn("flex flex-wrap gap-3", className)}>
      {links.map(({ kind, label, href }) => {
        const Icon = ICONS[kind];
        const external = href.startsWith("https://");
        return (
          <li key={kind} className="max-w-full">
            <a
              href={href}
              {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
              className={cn(buttonVariants({ variant: "outline", size: "lg" }), "h-auto min-h-11 max-w-full px-4 py-2 text-base break-all whitespace-normal")}
            >
              <Icon aria-hidden="true" />
              {label}
            </a>
          </li>
        );
      })}
    </ul>
  );
}
