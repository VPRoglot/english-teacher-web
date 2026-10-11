import Image from "next/image";

import type { HeroPublic } from "@/api/generated/model";

export function HeroSection({ hero }: { hero: HeroPublic }) {
  return (
    <section aria-labelledby="hero-title" className="bg-muted/40">
      <div className="mx-auto grid w-full max-w-5xl items-center gap-8 px-4 py-10 sm:px-6 md:grid-cols-2 md:py-16">
        <div className="space-y-4">
          <p className="text-sm font-medium text-muted-foreground">{hero.name}</p>
          <h1 id="hero-title" className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
            {hero.title}
          </h1>
          <p className="text-lg text-muted-foreground">{hero.subtitle}</p>
        </div>
        {hero.photo && (
          <Image
            src={hero.photo.url}
            width={hero.photo.width}
            height={hero.photo.height}
            alt={hero.name}
            unoptimized
            preload
            className="mx-auto h-auto max-h-[28rem] w-auto max-w-full rounded-2xl object-cover shadow-sm md:justify-self-end"
          />
        )}
      </div>
    </section>
  );
}
