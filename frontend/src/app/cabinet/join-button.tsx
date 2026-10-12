import { Button, buttonVariants } from "@/components/ui/button";

const LABEL = "Подключиться";
const NO_LINK_TEXT = "Ссылку пришлёт репетитор";

/** «Подключиться» к занятию; без ссылки кнопка неактивна, рядом подсказка. */
export function JoinButton({ url }: { url: string | null }) {
  if (url) {
    return (
      <a href={url} target="_blank" rel="noopener noreferrer" className={buttonVariants()}>
        {LABEL}
      </a>
    );
  }
  return (
    <span className="inline-flex items-center gap-2">
      <Button type="button" disabled>
        {LABEL}
      </Button>
      <span className="text-sm text-muted-foreground">{NO_LINK_TEXT}</span>
    </span>
  );
}
