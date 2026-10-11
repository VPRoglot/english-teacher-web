import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type SiteNavItem = { href: string; label: string };

export function SiteHeader({
  name,
  ctaText,
  nav,
  homeHref = "",
}: {
  name: string;
  ctaText: string;
  nav: SiteNavItem[];
  /** Префикс якорей `#top` и `#trial`: `"/"` на страницах, отличных от лендинга. */
  homeHref?: string;
}) {
  return (
    <header className="sticky top-0 z-40 border-b bg-background/90 backdrop-blur">
      <div className="mx-auto flex w-full max-w-5xl items-center gap-4 px-4 py-2.5 sm:px-6">
        <a href={`${homeHref}#top`} className="min-w-0 flex-1 truncate font-semibold md:flex-none">
          {name}
        </a>
        {nav.length > 0 && (
          <nav aria-label="Разделы сайта" className="hidden flex-1 items-center gap-1 md:flex">
            {nav.map(({ href, label }) => (
              <a
                key={href}
                href={href}
                className="rounded-lg px-2.5 py-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                {label}
              </a>
            ))}
          </nav>
        )}
        <a
          href={`${homeHref}#trial`}
          className={cn(
            buttonVariants({ size: "lg" }),
            "h-auto max-w-[60%] shrink-0 py-1.5 text-center text-xs leading-tight whitespace-normal sm:max-w-none sm:text-sm",
          )}
        >
          {ctaText}
        </a>
      </div>
    </header>
  );
}
