import type { ReactNode } from "react";

import type { ContactsBlock } from "@/api/generated/model";
import { contactLinks } from "@/lib/site-format";

import { ContactLinks } from "./contact-links";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-xl font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function Bullets({ items }: { items: string[] }) {
  return (
    <ul className="list-disc space-y-1 pl-6">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

/** Политика обработки персональных данных (152-ФЗ). */
export function PrivacyPolicy({
  operatorName,
  contacts,
}: {
  operatorName: string;
  contacts: ContactsBlock;
}) {
  const links = contactLinks(contacts);

  return (
    <article className="mx-auto w-full max-w-3xl space-y-8 px-4 py-10 leading-relaxed sm:px-6 md:py-14">
      <h1 className="text-3xl font-semibold tracking-tight">Политика обработки персональных данных</h1>

      <Section title="1. Оператор">
        <p>
          Оператор персональных данных на этом сайте — {operatorName} (далее — Оператор). Политика
          описывает, какие данные Оператор собирает, зачем, как долго хранит и как их можно
          удалить.
        </p>
      </Section>

      <Section title="2. Какие данные собираются">
        <p>При отправке заявки на пробное занятие:</p>
        <Bullets
          items={[
            "имя родителя;",
            "имя и возраст ребёнка;",
            "телефон или мессенджер для связи;",
            "комментарий к заявке;",
            "UTM-метки (источник перехода на сайт).",
          ]}
        />
        <p>При работе в личном кабинете:</p>
        <Bullets
          items={[
            "ФИО, email и телефон родителя;",
            "имя, год рождения, уровень английского и логин ребёнка;",
            "расписание занятий и заметки о занятиях.",
          ]}
        />
      </Section>

      <Section title="3. Цели обработки">
        <Bullets
          items={[
            "связаться с вами по заявке;",
            "проводить занятия;",
            "предоставить доступ к личному кабинету.",
          ]}
        />
      </Section>

      <Section title="4. Основание обработки">
        <p>
          Данные обрабатываются на основании вашего согласия. Данные ребёнка обрабатываются с
          согласия его законного представителя.
        </p>
      </Section>

      <Section title="5. Хранение">
        <p>Данные хранятся на серверах, расположенных в Российской Федерации.</p>
        <Bullets
          items={[
            "Заявки, по которым ребёнок не стал учеником, обезличиваются через 12 месяцев.",
            "Данные семьи хранятся до отзыва согласия и удаляются по вашему запросу.",
          ]}
        />
      </Section>

      <Section title="6. Передача третьим лицам">
        <p>
          Персональные данные не продаются и не передаются третьим лицам для их собственных целей.
          Краткое уведомление о новой заявке (имя, возраст ребёнка и способ связи) доставляется
          репетитору через Telegram.
        </p>
      </Section>

      <Section title="7. Cookie">
        <p>
          Сайт использует только технические cookie: сессия входа в личный кабинет и защита от
          подделки запросов (CSRF). Аналитические и рекламные cookie не используются.
        </p>
      </Section>

      <Section title="8. Права субъекта и отзыв согласия">
        <p>
          Вы вправе запросить сведения о ваших данных, их уточнение или удаление, а также отозвать
          согласие на обработку. Для этого свяжитесь с Оператором
          {links.length > 0 ? ":" : " по контактам, указанным на сайте."}
        </p>
        {links.length > 0 && <ContactLinks links={links} />}
      </Section>
    </article>
  );
}
