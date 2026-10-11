import Image from "next/image";

import type { ReviewPublic } from "@/api/generated/model";
import { Card, CardContent } from "@/components/ui/card";
import { pluralRu } from "@/lib/site-format";

export function ReviewsSection({ items }: { items: ReviewPublic[] }) {
  return (
    <section id="reviews" aria-labelledby="reviews-title" className="scroll-mt-16 py-12 sm:py-16">
      <div className="mx-auto w-full max-w-5xl px-4 sm:px-6">
        <h2 id="reviews-title" className="mb-6 text-2xl font-semibold tracking-tight">
          Отзывы
        </h2>
        <ul className="grid gap-4 md:grid-cols-2">
          {items.map((review, index) => (
            <li key={`${index}-${review.author}`} className="flex">
              <Card className="w-full">
                <CardContent className="space-y-4">
                  <blockquote className="whitespace-pre-line">{review.text}</blockquote>
                  <div className="flex items-center gap-3">
                    {review.photo && (
                      <Image
                        src={review.photo.url}
                        width={review.photo.width}
                        height={review.photo.height}
                        alt={review.author}
                        unoptimized
                        className="size-12 rounded-full object-cover"
                      />
                    )}
                    <div>
                      <p className="font-medium">{review.author}</p>
                      {review.child_age !== null && (
                        <p className="text-sm text-muted-foreground">
                          ребёнку {review.child_age} {pluralRu(review.child_age, ["год", "года", "лет"])}
                        </p>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
