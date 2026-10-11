import type { ServiceItem } from "@/api/generated/model";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatRub } from "@/lib/site-format";

export function ServicesSection({ items }: { items: ServiceItem[] }) {
  return (
    <section id="services" aria-labelledby="services-title" className="scroll-mt-16 bg-muted/40 py-12 sm:py-16">
      <div className="mx-auto w-full max-w-5xl px-4 sm:px-6">
        <h2 id="services-title" className="mb-6 text-2xl font-semibold tracking-tight">
          Услуги
        </h2>
        <ul className="grid gap-4 sm:grid-cols-2">
          {items.map((service, index) => (
            <li key={`${index}-${service.title}`} className="flex">
              <Card className="w-full">
                <CardHeader>
                  <CardTitle className="text-lg">{service.title}</CardTitle>
                  <CardDescription>
                    {service.duration_min} мин · {service.format}
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex flex-1 flex-col justify-between gap-4">
                  {service.description && <p>{service.description}</p>}
                  <p className="text-xl font-semibold">{formatRub(service.price_rub)}</p>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
