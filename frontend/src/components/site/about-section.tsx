import { CircleCheck } from "lucide-react";
import Image from "next/image";

import type { AboutPublic } from "@/api/generated/model";

import { Markdown } from "./markdown";

export function AboutSection({ about }: { about: AboutPublic }) {
  return (
    <section id="about" aria-labelledby="about-title" className="scroll-mt-16 py-12 sm:py-16">
      <div className="mx-auto w-full max-w-5xl px-4 sm:px-6">
        <h2 id="about-title" className="mb-6 text-2xl font-semibold tracking-tight">
          Обо мне
        </h2>
        <div className="grid gap-8 md:grid-cols-[1fr_16rem]">
          <div className="space-y-6">
            <Markdown>{about.text}</Markdown>
            {about.credentials.length > 0 && (
              <ul className="space-y-2">
                {about.credentials.map((credential) => (
                  <li key={credential} className="flex gap-2">
                    <CircleCheck aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-primary" />
                    <span>{credential}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {about.photo && (
            <Image
              src={about.photo.url}
              width={about.photo.width}
              height={about.photo.height}
              alt="Фото репетитора"
              unoptimized
              className="h-auto w-full max-w-xs justify-self-center rounded-2xl object-cover md:order-last"
            />
          )}
        </div>
      </div>
    </section>
  );
}
