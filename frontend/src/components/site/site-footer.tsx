import Link from "next/link";

export function SiteFooter({ name }: { name: string }) {
  return (
    <footer className="border-t bg-muted/40">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-3 px-4 py-8 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p>{name}</p>
        <nav aria-label="Служебные ссылки" className="flex flex-col gap-2 sm:flex-row sm:gap-6">
          <Link href="/privacy" className="underline-offset-4 hover:text-foreground hover:underline">
            Политика обработки персональных данных
          </Link>
          <Link href="/login" className="underline-offset-4 hover:text-foreground hover:underline">
            Вход для учеников
          </Link>
        </nav>
      </div>
    </footer>
  );
}
